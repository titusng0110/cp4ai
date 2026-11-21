import AppKit
import CP4AICore
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let progress = ProgressController()
    private var busy = false
    private var pending: [[URL]] = []
    private var idleExit: DispatchWorkItem?
    private var quickActionReceived = false

    func applicationWillFinishLaunching(_ notification: Notification) {
        NSApp.servicesProvider = self
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if Bundle.main.bundlePath.hasPrefix("/Volumes/") {
            AppLog.write("refusing to run from a mounted disk")
            let alert = NSAlert()
            alert.messageText = "Drag Copy 4 AI to Applications"
            alert.informativeText = "Copy 4 AI is running from the installer disk. Drag the app to Applications, then open it from there."
            alert.addButton(withTitle: "Quit")
            alert.runModal()
            NSApp.terminate(nil)
            return
        }
        removeLegacyQuickAction()
        CLIInstaller.installIfNeeded()
        scheduleIdleExit()
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        quickActionReceived = true
        idleExit?.cancel()
        idleExit = nil
        beginBatch(urls)
    }

    /// Finder Quick Action entry point (`NSMessage = copy4AI`).
    @objc func copy4AI(
        _ pasteboard: NSPasteboard,
        userData: String,
        error: AutoreleasingUnsafeMutablePointer<NSString>
    ) {
        quickActionReceived = true
        idleExit?.cancel()
        idleExit = nil

        let objects = pasteboard.readObjects(
            forClasses: [NSURL.self],
            options: [.urlReadingFileURLsOnly: true]
        )
        let urls = (objects as? [NSURL])?.map { $0 as URL } ?? []
        guard !urls.isEmpty else {
            error.pointee = "Select DOCX, PDF or PPTX files, not folders." as NSString
            return
        }
        beginBatch(urls)
    }

    private func beginBatch(_ urls: [URL]) {
        let (valid, rejected) = SourceFilter.filter(urls)
        guard !valid.isEmpty else {
            let reason = rejected.first?.1 ?? "no supported files"
            progress.failure("Select DOCX, PDF or PPTX files, not folders.\n\(reason)")
            return
        }
        let sources = SourceFilter.sortedByName(valid)
        if busy {
            pending.append(sources)
            progress.queued()
            return
        }

        busy = true
        progress.begin(count: sources.count, skipped: rejected.count)
        AppLog.write("starting batch: \(sources.map(\.lastPathComponent).joined(separator: ", "))")

        let options = ConversionOptions.quickAction()
        let engine = ConversionEngine(options: options)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                let result = try engine.convertBatch(sources: sources) { event in
                    DispatchQueue.main.async {
                        self?.handle(event)
                    }
                }
                DispatchQueue.main.async {
                    self?.finishSuccess(result)
                }
            } catch let failure as BatchFailure {
                let message: String
                if let first = failure.errors.first {
                    message = first.message
                    AppLog.write("conversion failed for \(first.source.lastPathComponent): \(first.message)")
                } else {
                    message = "conversion failed"
                }
                DispatchQueue.main.async {
                    self?.finishFailure(message)
                }
            } catch {
                AppLog.write("conversion failed: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    self?.finishFailure(error.localizedDescription)
                }
            }
        }
    }

    private func handle(_ event: ProgressEvent) {
        switch event {
        case .work(let state):
            progress.updateWork(state)
        case .fileStarted(let index, let total, let source):
            progress.updateFile(index: index, total: total, name: source.lastPathComponent, error: nil)
        case .fileFinished(let index, let total, let source, _, let error):
            progress.updateFile(index: index, total: total, name: source.lastPathComponent, error: error)
        }
    }

    private func finishSuccess(_ result: BatchResult) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        guard pasteboard.setString(result.markdown, forType: .string) else {
            finishFailure("could not write to the clipboard")
            return
        }
        AppLog.write("copied \(result.characters) characters / \(result.tokens) tokens")
        progress.success(characters: result.characters, tokens: result.tokens)
        busy = false

        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            guard let self else { return }
            if self.pending.isEmpty {
                NSApp.terminate(nil)
            } else {
                let next = self.pending.removeFirst()
                self.beginBatch(next)
            }
        }
    }

    private func finishFailure(_ message: String) {
        progress.failure(message)
        busy = false
        // Leave the panel open so the user can read the error.
    }

    private func scheduleIdleExit() {
        guard !quickActionReceived else { return }
        idleExit?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.busy, self.pending.isEmpty else { return }
            NSApp.terminate(nil)
        }
        idleExit = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0, execute: work)
    }

    /// The 3.x app installed an Automator workflow. The Swift app provides the
    /// same menu item natively, so remove the old copy to avoid duplicates.
    private func removeLegacyQuickAction() {
        let services = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Services")
        var removed = false
        for name in ["Copy 4 AI.workflow", "Copy for AI.workflow"] {
            let workflow = services.appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: workflow.path) {
                try? FileManager.default.removeItem(at: workflow)
                removed = true
                AppLog.write("removed legacy Finder action: \(workflow.path)")
            }
        }
        if removed {
            _ = try? ProcessRunner.run(
                URL(fileURLWithPath: "/System/Library/CoreServices/pbs"),
                ["-flush"]
            )
        }
    }
}
