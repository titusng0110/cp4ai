import Foundation

public final class PDFPipeline {
    public static let ocrComment = "<!-- OCR text from image(s) on this page; the text existed only inside a picture and may contain recognition errors -->"

    private let helper: PDFHelperClient
    private let ocr: OCRService
    private let cache: OCRCache
    private let useOCR: Bool
    private let onPage: PageHandler?
    private let onOCR: OCRHandler?

    public init(
        helper: PDFHelperClient,
        ocr: OCRService,
        cache: OCRCache,
        useOCR: Bool,
        onPage: PageHandler?,
        onOCR: OCRHandler?
    ) {
        self.helper = helper
        self.ocr = ocr
        self.cache = cache
        self.useOCR = useOCR
        self.onPage = onPage
        self.onOCR = onOCR
    }

    public func convert(_ source: URL, to output: URL) throws -> String {
        let regions = try TemporaryDirectory(prefix: "cp4ai_pdf_")
        let document = try helper.extract(source, output: regions.url)
        let total = document.pages.count
        var parts: [String] = []
        var ocrPages = 0

        for (index, page) in document.pages.enumerated() {
            let native = TextTools.clean(page.markdown)
            var ocrText = ""
            if useOCR {
                ocrText = ocrPage(page, outputDirectory: regions.url, nativeText: native)
                if !ocrText.isEmpty, TextTools.tokenSet(ocrText).isSubset(of: TextTools.tokenSet(native)) {
                    ocrText = ""
                }
            }
            if !ocrText.isEmpty { ocrPages += 1 }

            var body = native
            if !ocrText.isEmpty {
                body += "\n\n\(Self.ocrComment)\n\n\(ocrText)"
            }
            parts.append("<!-- page \(index + 1) of \(total) -->\n\n\(body.trimmingCharacters(in: .whitespacesAndNewlines))")
            onPage?()
        }

        let header = TextTools.frontMatter(
            path: source,
            format: "pdf",
            extras: [
                ("pages", String(total)),
                ("text_extraction", "pymupdf \(document.pymupdf)"),
                (
                    "images_ocr",
                    useOCR
                        ? "\(ocr.label) (\(ocrPages) page(s) with OCR text)"
                        : "disabled"
                ),
            ]
        )
        let markdown = "\(header)\n\n# \(TextTools.title(of: source))\n\n" + parts.joined(separator: "\n\n")
        try TextTools.writeMarkdown(markdown, to: output)
        return "pdf, \(total) pages, OCR on \(ocrPages) page(s)"
    }

    private func ocrPage(_ page: PDFPage, outputDirectory: URL, nativeText: String) -> String {
        let nativeTokens = TextTools.tokenSet(nativeText).count
        var regions = ocrRegions(page.foreground, outputDirectory: outputDirectory)

        if !page.foreground.isEmpty {
            let ocrTokens = TextTools.tokenSet(regions.joined(separator: "\n")).count
            if nativeTokens < 40, ocrTokens < 20, !page.background.isEmpty {
                regions = ocrRegions(page.background, outputDirectory: outputDirectory)
            }
        } else if !page.background.isEmpty, nativeTokens < 40 {
            regions = ocrRegions(page.background, outputDirectory: outputDirectory)
        }
        return regions.joined(separator: "\n\n")
    }

    private func ocrRegions(_ regions: [PDFRegion], outputDirectory: URL) -> [String] {
        var results: [String] = []
        for region in regions {
            let file = outputDirectory.appendingPathComponent(region.file)
            let text: String
            if let cached = cache.text(for: region.sha256) {
                text = cached
            } else {
                text = (try? ocr.recognize(imageAt: file)) ?? ""
                cache.store(text, for: region.sha256)
            }
            onOCR?()
            if !text.isEmpty, TextTools.usefulOCR(text) {
                results.append(text)
            }
        }
        return results
    }
}
