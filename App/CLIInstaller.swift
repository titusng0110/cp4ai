import CP4AICore
import Foundation

/// Installs `cp4ai` and `md4ai` symlinks and makes `~/.local/bin` available in
/// zsh. Runs from the app's first launch, so dragging the app to Applications
/// installs everything: the Quick Action and the command-line tools.
enum CLIInstaller {
    private static let markerStart = "# >>> Copy 4 AI command-line tools >>>"
    private static let markerEnd = "# <<< Copy 4 AI command-line tools <<<"

    static func installIfNeeded() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let bundle = Bundle.main.bundleURL.standardizedFileURL.path
        guard bundle.hasPrefix("/Applications/") || bundle.hasPrefix(home.path + "/Applications/") else {
            return
        }

        let cli = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/cp4ai")
        guard FileManager.default.isExecutableFile(atPath: cli.path) else {
            AppLog.write("CLI install skipped: \(cli.path) is missing")
            return
        }

        let directory = home.appendingPathComponent(".local/bin")
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            AppLog.write("CLI install failed: \(error.localizedDescription)")
            return
        }

        for name in ["cp4ai", "md4ai"] {
            let link = directory.appendingPathComponent(name)
            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(atPath: link.path, isDirectory: &isDirectory) {
                let destination = try? FileManager.default.destinationOfSymbolicLink(atPath: link.path)
                if destination == nil {
                    AppLog.write("CLI install skipped: \(link.path) is not a symlink")
                    continue
                }
                try? FileManager.default.removeItem(at: link)
            }
            do {
                try FileManager.default.createSymbolicLink(at: link, withDestinationURL: cli)
                AppLog.write("installed CLI: \(link.path) -> \(cli.path)")
            } catch {
                AppLog.write("CLI install failed for \(link.path): \(error.localizedDescription)")
            }
        }

        installPath(in: home.appendingPathComponent(".zprofile"))
    }

    /// Adds ~/.local/bin to PATH once, using a clearly marked block.
    private static func installPath(in profile: URL) {
        let block = """
        \(markerStart)
        export PATH="$HOME/.local/bin:$PATH"
        \(markerEnd)

        """
        if let existing = try? String(contentsOf: profile, encoding: .utf8) {
            if existing.contains(markerStart) { return }
            let handle: FileHandle
            do {
                handle = try FileHandle(forWritingTo: profile)
            } catch {
                AppLog.write("could not update \(profile.path): \(error.localizedDescription)")
                return
            }
            defer { try? handle.close() }
            try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(("\n" + block).utf8))
            AppLog.write("added ~/.local/bin to PATH in \(profile.path)")
        } else {
            try? block.write(to: profile, atomically: true, encoding: .utf8)
            AppLog.write("created \(profile.path) with ~/.local/bin on PATH")
        }
    }
}
