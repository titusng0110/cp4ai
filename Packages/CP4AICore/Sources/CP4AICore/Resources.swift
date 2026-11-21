import Foundation

/// Locations for every bundled tool and data file.
///
/// The app resolves resources from ``Copy 4 AI.app/Contents/Resources``.  A
/// CLI binary inside the bundle (or a symlink to it) resolves through its real
/// path.  During development the same locator finds `packaging/native` and
/// `build/pdf-helper` in the repository.
public struct CP4AIResources {
    public let root: URL
    public let pandocOverride: URL?
    public let pdfHelperOverride: URL?
    public let tokenizerOverride: URL?

    public init(
        root: URL,
        pandocOverride: URL? = nil,
        pdfHelperOverride: URL? = nil,
        tokenizerOverride: URL? = nil
    ) {
        self.root = root
        self.pandocOverride = pandocOverride
        self.pdfHelperOverride = pdfHelperOverride
        self.tokenizerOverride = tokenizerOverride
    }

    private static let fileManager = FileManager.default

    public static func locate() -> CP4AIResources {
        let environment = ProcessInfo.processInfo.environment
        let pandocOverride = executableOverride(environment["CP4AI_PANDOC"])
        let pdfOverride = executableOverride(environment["CP4AI_PDF_HELPER"])
        let tokenizerOverride = existingFile(environment["CP4AI_TOKENIZER"])

        if let raw = environment["CP4AI_RESOURCES"], !raw.isEmpty {
            return CP4AIResources(
                root: URL(fileURLWithPath: raw).standardizedFileURL,
                pandocOverride: pandocOverride,
                pdfHelperOverride: pdfOverride,
                tokenizerOverride: tokenizerOverride
            )
        }

        for candidate in resourceCandidates() where fileManager.fileExists(atPath: candidate.appendingPathComponent("bin/pandoc").path) {
            return CP4AIResources(
                root: candidate,
                pandocOverride: pandocOverride,
                pdfHelperOverride: pdfOverride,
                tokenizerOverride: tokenizerOverride
            )
        }

        if let repo = repositoryRoot() {
            let native = repo.appendingPathComponent("packaging/native")
            return CP4AIResources(
                root: native,
                pandocOverride: pandocOverride,
                pdfHelperOverride: pdfOverride,
                tokenizerOverride: tokenizerOverride
            )
        }

        return CP4AIResources(
            root: Bundle.main.resourceURL ?? URL(fileURLWithPath: fileManager.currentDirectoryPath),
            pandocOverride: pandocOverride,
            pdfHelperOverride: pdfOverride,
            tokenizerOverride: tokenizerOverride
        )
    }

    public var binDirectory: URL { root.appendingPathComponent("bin") }

    public var pandoc: URL? {
        if let pandocOverride { return pandocOverride }
        let bundled = binDirectory.appendingPathComponent("pandoc")
        if Self.fileManager.isExecutableFile(atPath: bundled.path) { return bundled }
        return Self.which("pandoc")
    }

    public var rsvgConvert: URL? {
        let bundled = binDirectory.appendingPathComponent("rsvg-convert")
        if Self.fileManager.isExecutableFile(atPath: bundled.path) { return bundled }
        return Self.which("rsvg-convert")
    }

    public var emf2svgConvert: URL? {
        let bundled = binDirectory.appendingPathComponent("emf2svg-conv")
        if Self.fileManager.isExecutableFile(atPath: bundled.path) { return bundled }
        return Self.which("emf2svg-conv")
    }

    public var pdfHelper: URL? {
        if let pdfHelperOverride { return pdfHelperOverride }
        let install = root.appendingPathComponent("pdf-helper/cp4ai-pdf")
        if Self.fileManager.isExecutableFile(atPath: install.path) { return install }

        guard let repo = Self.repositoryRoot() else { return nil }
        let built = repo.appendingPathComponent("build/pdf-helper/cp4ai-pdf")
        if Self.fileManager.isExecutableFile(atPath: built.path) { return built }
        let dist = repo.appendingPathComponent("helper/dist/cp4ai-pdf/cp4ai-pdf")
        if Self.fileManager.isExecutableFile(atPath: dist.path) { return dist }
        return nil
    }

    public var tokenizer: URL? {
        if let tokenizerOverride { return tokenizerOverride }
        for name in ["9b5ad71b2ce5302211f9c61530b329a4922fc6a4", "cl100k_base.tiktoken"] {
            let direct = root.appendingPathComponent("tiktoken/\(name)")
            if Self.fileManager.fileExists(atPath: direct.path) { return direct }
            if let repo = Self.repositoryRoot() {
                let nested = repo.appendingPathComponent("packaging/native/tiktoken/\(name)")
                if Self.fileManager.fileExists(atPath: nested.path) { return nested }
            }
        }
        return nil
    }

    public var fontsConf: URL? {
        let candidates = [
            root.appendingPathComponent("fonts.conf"),
            root.appendingPathComponent("etc/fonts/fonts.conf"),
        ]
        for candidate in candidates where Self.fileManager.fileExists(atPath: candidate.path) {
            return candidate
        }
        if let repo = Self.repositoryRoot() {
            let candidate = repo.appendingPathComponent("Resources/fonts.conf")
            if Self.fileManager.fileExists(atPath: candidate.path) { return candidate }
        }
        return nil
    }

    public func environment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        if let fontsConf {
            environment["FONTCONFIG_PATH"] = fontsConf.deletingLastPathComponent().path
            environment["FONTCONFIG_FILE"] = fontsConf.path
        }
        return environment
    }

    private static func resourceCandidates() -> [URL] {
        var candidates: [URL] = []
        if let resources = Bundle.main.resourceURL {
            candidates.append(resources)
        }

        let executable = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        if let contents = executable.path.split(separator: "/").dropLast().last,
           contents == "MacOS" {
            let macos = executable.deletingLastPathComponent()
            candidates.append(macos.deletingLastPathComponent().appendingPathComponent("Resources"))
        }

        // Xcode Debug builds: <products>/Debug/Copy 4 AI.app/Contents/Resources
        candidates.append(executable.deletingLastPathComponent())

        if let repo = repositoryRoot() {
            candidates.append(repo.appendingPathComponent("packaging/native"))
        }
        return candidates
    }

    public static func repositoryRoot() -> URL? {
        let starts = [
            URL(fileURLWithPath: fileManager.currentDirectoryPath),
            URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath().deletingLastPathComponent(),
        ]
        for start in starts {
            var directory = start
            for _ in 0..<10 {
                let version = directory.appendingPathComponent("VERSION")
                let package = directory.appendingPathComponent("Packages/CP4AICore")
                if fileManager.fileExists(atPath: version.path), fileManager.fileExists(atPath: package.path) {
                    return directory
                }
                let parent = directory.deletingLastPathComponent()
                if parent.path == directory.path { break }
                directory = parent
            }
        }
        return nil
    }

    private static func executableOverride(_ raw: String?) -> URL? {
        guard let raw, !raw.isEmpty else { return nil }
        let url = URL(fileURLWithPath: raw).standardizedFileURL
        return fileManager.isExecutableFile(atPath: url.path) ? url : nil
    }

    private static func existingFile(_ raw: String?) -> URL? {
        guard let raw, !raw.isEmpty else { return nil }
        let url = URL(fileURLWithPath: raw).standardizedFileURL
        return fileManager.fileExists(atPath: url.path) ? url : nil
    }

    public static func which(_ name: String) -> URL? {
        let environment = ProcessInfo.processInfo.environment
        let path = environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        for directory in path.split(separator: ":") {
            let candidate = URL(fileURLWithPath: String(directory)).appendingPathComponent(name)
            if fileManager.isExecutableFile(atPath: candidate.path) {
                return candidate
            }
        }
        return nil
    }
}
