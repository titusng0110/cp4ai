import Foundation

public struct ProcessOutput {
    public let status: Int32
    public let stdout: String
    public let stderr: String

    public var succeeded: Bool { status == 0 }
}

public enum ProcessRunner {
    /// Run a process and capture both streams without deadlocking on a full pipe.
    public static func run(
        _ executable: URL,
        _ arguments: [String],
        cwd: URL? = nil,
        environment: [String: String]? = nil
    ) throws -> ProcessOutput {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        if let cwd { process.currentDirectoryURL = cwd }
        if let environment { process.environment = environment }

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        do {
            try process.run()
        } catch {
            throw ConversionError.processFailed(
                "could not run \(executable.lastPathComponent): \(error.localizedDescription)"
            )
        }

        var stderrData = Data()
        let stderrQueue = DispatchQueue(label: "cp4ai.stderr")
        stderrQueue.async {
            stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        }
        let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        stderrQueue.sync {}

        return ProcessOutput(
            status: process.terminationStatus,
            stdout: String(decoding: stdoutData, as: UTF8.self),
            stderr: String(decoding: stderrData, as: UTF8.self)
        )
    }

    public static func which(_ name: String) -> URL? {
        CP4AIResources.which(name)
    }
}

public final class TemporaryDirectory {
    public let url: URL

    public init(prefix: String) throws {
        let base = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        let candidate = base.appendingPathComponent("\(prefix)\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: candidate, withIntermediateDirectories: true)
        url = candidate
    }

    deinit {
        try? FileManager.default.removeItem(at: url)
    }
}
