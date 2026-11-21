import Foundation

public final class ConversionEngine {
    public let options: ConversionOptions
    private let pandoc: PandocRunner
    private let ocr: OCRService
    private let renderer: VectorRenderer
    private let pdfHelper: PDFHelperClient
    private let tokenizer: TokenCounter?

    public init(options: ConversionOptions) {
        self.options = options
        pandoc = PandocRunner(resources: options.resources)
        ocr = OCRService(languages: options.ocrLanguages)
        renderer = VectorRenderer(resources: options.resources)
        pdfHelper = PDFHelperClient(resources: options.resources)
        if let url = options.resources.tokenizer, let counter = try? TokenCounter(vocabURL: url) {
            tokenizer = counter
        } else {
            tokenizer = nil
        }
    }

    public func convertOne(
        _ source: URL,
        to output: URL,
        onPage: PageHandler? = nil,
        onOCR: OCRHandler? = nil
    ) throws -> String {
        switch source.pathExtension.lowercased() {
        case "docx":
            return try convertDOCX(source, output: output, onOCR: onOCR)
        case "pptx":
            return try convertPPTX(source, output: output, onPage: onPage, onOCR: onOCR)
        case "pdf":
            return try convertPDF(source, output: output, onPage: onPage, onOCR: onOCR)
        default:
            throw ConversionError.unsupported("unsupported file type: \(source.path)")
        }
    }

    public func convertBatch(
        sources: [URL],
        outputURLs: [URL]? = nil,
        progress: ProgressHandler? = nil
    ) throws -> BatchResult {
        precondition(!sources.isEmpty, "convertBatch needs at least one source")
        if let outputURLs {
            precondition(outputURLs.count == sources.count, "output count must match sources")
        }

        let temporary: TemporaryDirectory?
        let outputs: [URL]
        if let outputURLs {
            outputs = outputURLs
            temporary = nil
        } else {
            let directory = try TemporaryDirectory(prefix: "cp4ai_clipboard_")
            temporary = directory
            outputs = sources.indices.map { directory.url.appendingPathComponent(String(format: "%04d.md", $0)) }
        }
        _ = temporary

        var work = WorkState(pagesTotal: 0, ocrTotal: 0)
        let totals = countWork(sources)
        work.pagesTotal = totals.pages
        work.ocrTotal = totals.ocr
        progress?(.work(work))

        let lock = NSLock()
        var errors: [FileFailure] = []
        var rendered: [Int: String] = [:]

        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = max(1, min(options.jobs, sources.count))
        queue.qualityOfService = .userInitiated

        for (index, source) in sources.enumerated() {
            let output = outputs[index]
            queue.addOperation { [weak self] in
                guard let self else { return }
                progress?(.fileStarted(index: index + 1, total: sources.count, source: source))

                let onPage: PageHandler = {
                    lock.lock()
                    work.pagesDone += 1
                    let snapshot = work
                    lock.unlock()
                    progress?(.work(snapshot))
                }
                let onOCR: OCRHandler = {
                    lock.lock()
                    work.ocrDone += 1
                    let snapshot = work
                    lock.unlock()
                    progress?(.work(snapshot))
                }

                do {
                    let details = try self.convertOne(source, to: output, onPage: onPage, onOCR: onOCR)
                    let body = (try? String(contentsOf: output, encoding: .utf8)) ?? ""
                    lock.lock()
                    rendered[index] = body
                    lock.unlock()
                    progress?(.fileFinished(index: index + 1, total: sources.count, source: source, details: details, error: nil))
                } catch {
                    let message = error.localizedDescription
                    lock.lock()
                    errors.append(FileFailure(source: source, message: message))
                    lock.unlock()
                    progress?(.fileFinished(index: index + 1, total: sources.count, source: source, details: nil, error: message))
                }
            }
        }
        queue.waitUntilAllOperationsAreFinished()

        if !errors.isEmpty {
            throw BatchFailure(errors: errors.sorted { $0.source.lastPathComponent < $1.source.lastPathComponent })
        }

        var sections: [String] = []
        for (index, source) in sources.enumerated() {
            let body = (rendered[index] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            sections.append("[\(source.lastPathComponent) BEGIN]\n\(body)\n[\(source.lastPathComponent) END]")
        }
        let markdown = sections.joined(separator: "\n\n") + "\n"
        let tokens = tokenizer?.count(markdown) ?? 0
        return BatchResult(
            markdown: markdown,
            characters: markdown.unicodeScalars.count,
            tokens: tokens,
            files: sources
        )
    }

    public func countWork(_ sources: [URL]) -> WorkTotals {
        var totals = WorkTotals()
        for source in sources {
            switch source.pathExtension.lowercased() {
            case "pdf":
                if let probe = try? pdfHelper.probe(source) {
                    totals.pages += probe.pageCount
                    totals.ocr += probe.ocrJobs
                }
            case "docx":
                totals.pages += 1
                if let archive = try? OfficeArchive(url: source) {
                    totals.ocr += archive.files(in: "word/media").filter {
                        DocxImageProcessor.imageSuffixes.contains("." + ($0 as NSString).pathExtension.lowercased())
                    }.count
                }
            case "pptx":
                let slides = PptxMetadata.slides(at: source)
                totals.pages += slides.count
                totals.ocr += slides.reduce(0) { $0 + $1.images.count }
            default:
                break
            }
        }
        return totals
    }

    // MARK: - DOCX

    private func convertDOCX(_ source: URL, output: URL, onOCR: OCRHandler?) throws -> String {
        try FileManager.default.createDirectory(
            at: output.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let temporary = try TemporaryDirectory(prefix: "cp4ai_docx_")
        let pandocBody = try pandoc.convertDOCX(source, workdir: temporary.url)
        let mediaDir = temporary.url.appendingPathComponent("media")
        let cache = OCRCache()
        let processor = DocxImageProcessor(
            mediaDir: mediaDir,
            workdir: temporary.url,
            ocr: ocr,
            cache: cache,
            renderer: renderer,
            useOCR: options.useOCR,
            onOCR: onOCR
        )

        var body = processor.replaceImages(in: pandocBody)
        let figures = processor.figuresSection()
        processor.addFailedVectors(figures.failed)
        let comments = DocxMetadata.comments(at: source)
        let inserted = CommentPlacement.insert(markdown: body, comments: comments)
        body = inserted.markdown
        let header = DocxMetadata.header(at: source)

        let front = TextTools.frontMatter(
            path: source,
            format: "docx",
            extras: [
                ("converter", "pandoc \(pandoc.version)"),
                ("header", header.isEmpty ? nil : header),
                ("comments", comments.isEmpty ? nil : String(comments.count)),
                ("images_ocr", options.useOCR ? ocr.label : "disabled"),
            ]
        )

        var pieces = [front, "", "# \(TextTools.title(of: source))", ""]
        if !header.isEmpty {
            pieces.append("> **Original document header:** \(header)")
            pieces.append("")
        }
        pieces.append(body)
        pieces.append("")
        pieces.append(figures.section)
        pieces.append(CommentPlacement.appendix(inserted.unplaced))
        pieces.append(processor.vectorNote())

        try TextTools.writeMarkdown(pieces.joined(separator: "\n"), to: output)
        return "docx, \(comments.count) comment(s), \(figures.count) floating figure(s), \(processor.failedVectorFiles().count) vector image(s) not OCR'd"
    }

    // MARK: - PPTX

    private func convertPPTX(_ source: URL, output: URL, onPage: PageHandler?, onOCR: OCRHandler?) throws -> String {
        try FileManager.default.createDirectory(
            at: output.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let metadata = PptxMetadata.slides(at: source)
        let temporary = try TemporaryDirectory(prefix: "cp4ai_pptx_")
        let pandocBody = try pandoc.convertPPTX(source, workdir: temporary.url)
        let mediaDir = temporary.url.appendingPathComponent("media")
        let cache = OCRCache()
        let processor = PptxPostProcessor(
            mediaDir: mediaDir,
            workdir: temporary.url,
            ocr: ocr,
            cache: cache,
            renderer: renderer,
            useOCR: options.useOCR,
            onOCR: onOCR
        )

        var split = processor.splitSlides(pandocBody)
        if !split.preamble.isEmpty, !split.chunks.isEmpty {
            split.chunks[0] = split.preamble + "\n\n" + split.chunks[0]
        } else if !split.preamble.isEmpty {
            split.chunks = [split.preamble]
        }

        let total = max(split.chunks.count, metadata.count)
        var rendered: [String] = []
        for index in 0..<total {
            let chunk = index < split.chunks.count ? split.chunks[index] : ""
            let meta = index < metadata.count ? metadata[index] : PptxSlideMeta()
            let withImages = processor.replaceImages(
                in: chunk,
                imageCoords: meta.images,
                slideWidth: meta.width,
                slideHeight: meta.height
            )
            let withMeta = processor.appendSlideMeta(withImages, meta: meta)
            var body = "<!-- slide \(index + 1) of \(total) -->"
            if !withMeta.isEmpty {
                body += "\n\n\(withMeta)"
            }
            rendered.append(body)
            onPage?()
        }

        let noteCount = metadata.filter { !$0.notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.count
        let commentCount = metadata.reduce(0) { $0 + $1.comments.count }
        let header = TextTools.frontMatter(
            path: source,
            format: "pptx",
            extras: [
                ("converter", "pandoc \(pandoc.version)"),
                ("slides", String(metadata.isEmpty ? total : metadata.count)),
                ("notes", noteCount == 0 ? nil : String(noteCount)),
                ("comments", commentCount == 0 ? nil : String(commentCount)),
                ("images_ocr", options.useOCR ? ocr.label : "disabled"),
            ]
        )
        try TextTools.writeMarkdown("\(header)\n\n# \(TextTools.title(of: source))\n\n" + rendered.joined(separator: "\n\n"), to: output)
        return "pptx, \(metadata.isEmpty ? total : metadata.count) slide(s), \(noteCount) note(s), \(commentCount) comment(s)"
    }

    // MARK: - PDF

    private func convertPDF(_ source: URL, output: URL, onPage: PageHandler?, onOCR: OCRHandler?) throws -> String {
        let pipeline = PDFPipeline(
            helper: pdfHelper,
            ocr: ocr,
            cache: OCRCache(),
            useOCR: options.useOCR,
            onPage: onPage,
            onOCR: onOCR
        )
        return try pipeline.convert(source, to: output)
    }
}
