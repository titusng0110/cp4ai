import Foundation

public final class PandocRunner {
    private let resources: CP4AIResources
    private var cachedVersion: String?
    private let versionLock = NSLock()

    public init(resources: CP4AIResources) {
        self.resources = resources
    }

    public var executable: URL {
        get throws {
            guard let pandoc = resources.pandoc else {
                throw ConversionError.missingTool(
                    "pandoc not found. The app bundles it; a development build needs packaging/native/bin/pandoc."
                )
            }
            return pandoc
        }
    }

    public var version: String {
        versionLock.lock()
        defer { versionLock.unlock() }
        if let cachedVersion { return cachedVersion }
        let value: String
        do {
            let output = try ProcessRunner.run(try executable, ["--version"], environment: resources.environment())
            let first = output.stdout.components(separatedBy: "\n").first ?? ""
            if first.lowercased().hasPrefix("pandoc") {
                value = String(first.dropFirst(6)).trimmingCharacters(in: .whitespaces)
            } else {
                value = first.isEmpty ? "unknown" : first
            }
        } catch {
            value = "unknown"
        }
        cachedVersion = value
        return value
    }

    public func convertDOCX(_ input: URL, workdir: URL) throws -> String {
        let output = try ProcessRunner.run(
            try executable,
            [
                input.standardizedFileURL.path,
                "--from=docx",
                "--to=gfm",
                "--wrap=none",
                "--markdown-headings=atx",
                "--track-changes=all",
                "--extract-media=media",
            ],
            cwd: workdir,
            environment: resources.environment()
        )
        guard output.succeeded else {
            throw ConversionError.processFailed("Pandoc failed for \(input.path):\n\(output.stderr)")
        }
        return output.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public func convertPPTX(_ input: URL, workdir: URL) throws -> String {
        let output = try ProcessRunner.run(
            try executable,
            [
                input.standardizedFileURL.path,
                "--from=pptx",
                "--to=gfm",
                "--wrap=none",
                "--markdown-headings=atx",
                "--extract-media=media",
            ],
            cwd: workdir,
            environment: resources.environment()
        )
        guard output.succeeded else {
            throw ConversionError.processFailed("Pandoc failed for \(input.path):\n\(output.stderr)")
        }
        return output.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
