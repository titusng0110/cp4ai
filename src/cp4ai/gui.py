"""Native macOS progress popup and app delegate for Copy 4 AI."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAlertSecondButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSLineBreakByTruncatingMiddle,
    NSMakeRect,
    NSProgressIndicator,
    NSProgressIndicatorStyleBar,
    NSTextField,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from .pipeline import (
    BatchFailure,
    convert_batch,
    copy_to_clipboard,
    filter_sources,
    sort_sources,
)

logger = logging.getLogger(__name__)
_delegate = None


def _configure_logging() -> None:
    package_logger = logging.getLogger("cp4ai")
    if package_logger.handlers:
        return
    log_dir = Path.home() / "Library" / "Logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "Copy 4 AI.log",
            maxBytes=2_000_000,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    package_logger.addHandler(handler)
    package_logger.setLevel(logging.DEBUG)


def _label(text: str, frame, size: float, bold: bool = False) -> NSTextField:
    label = NSTextField.labelWithString_(text)
    label.setFrame_(frame)
    label.setFont_(
        NSFont.boldSystemFontOfSize_(size)
        if bold
        else NSFont.systemFontOfSize_(size)
    )
    label.setLineBreakMode_(NSLineBreakByTruncatingMiddle)
    label.setMaximumNumberOfLines_(1)
    return label


class ProgressController(NSObject):
    def initWithOptions_(self, options):
        self = objc.super(ProgressController, self).init()
        if self is None:
            return None
        self.engine = options.get("engine", "livetext")
        self.use_ocr = bool(options.get("use_ocr", True))
        self.jobs = int(options.get("jobs", 1))
        self.busy = False
        self.pending: list[Path] | None = None
        self._close_timer = None
        self._build_window()
        return self

    # -- UI ---------------------------------------------------------------

    def _build_window(self) -> None:
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 360, 100),
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("Copy 4 AI")
        window.setMovableByWindowBackground_(True)
        window.setLevel_(NSFloatingWindowLevel)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        window.setReleasedWhenClosed_(False)
        window.setDelegate_(self)
        window.center()
        self.window = window

        content = window.contentView()
        self.status_label = _label("Ready", NSMakeRect(20, 62, 320, 18), 12, bold=True)
        content.addSubview_(self.status_label)

        self.bar = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(20, 38, 320, 12)
        )
        self.bar.setStyle_(NSProgressIndicatorStyleBar)
        self.bar.setIndeterminate_(False)
        self.bar.setMinValue_(0.0)
        self.bar.setMaxValue_(100.0)
        self.bar.setDoubleValue_(0.0)
        content.addSubview_(self.bar)

        self.detail_label = _label("", NSMakeRect(20, 14, 260, 16), 10)
        self.detail_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.detail_label)

        self.close_button = NSButton.alloc().initWithFrame_(
            NSMakeRect(296, 6, 52, 26)
        )
        self.close_button.setTitle_("Close")
        self.close_button.setBezelStyle_(NSBezelStyleRounded)
        self.close_button.setTarget_(self)
        self.close_button.setAction_("close:")
        self.close_button.setHidden_(True)
        content.addSubview_(self.close_button)

    def _show(self) -> None:
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    @objc.python_method
    def _set_indeterminate(self, on: bool) -> None:
        self.bar.setIndeterminate_(on)
        if on:
            self.bar.startAnimation_(None)
        else:
            self.bar.stopAnimation_(None)

    # -- lifecycle --------------------------------------------------------

    def beginBatch_(self, paths) -> None:
        if self.busy:
            self.pending = [Path(path) for path in paths]
            self.status_label.setStringValue_("Another batch queued…")
            self._show()
            return

        if self._close_timer is not None:
            self._close_timer.invalidate()
            self._close_timer = None

        sources, rejected = filter_sources(paths)
        if not sources:
            reason = rejected[0].reason if rejected else "no supported files"
            self._fail_with_message(
                "No supported files",
                f"Select DOCX, PDF, or PPTX files, not folders.\n{reason}",
            )
            return

        sources = sort_sources(sources)
        self.busy = True
        self.pending = None
        self.close_button.setHidden_(True)
        self.detail_label.setStringValue_("")
        self.detail_label.setToolTip_("")
        if rejected:
            self.status_label.setStringValue_(
                f"Processing {len(sources)} file(s), {len(rejected)} skipped…"
            )
        else:
            self.status_label.setStringValue_(f"Processing {len(sources)} file(s)…")
        self._set_indeterminate(True)
        self.bar.setDoubleValue_(0.0)
        self._show()

        thread = threading.Thread(
            target=self._worker,
            args=(sources,),
            daemon=True,
        )
        thread.start()

    @objc.python_method
    def _worker(self, sources: list[Path]) -> None:
        try:
            result = convert_batch(
                sources,
                engine=self.engine,
                use_ocr=self.use_ocr,
                jobs=self.jobs,
                progress=self._progress,
                work_progress=self._work_progress,
                force_process=True,
            )
        except BatchFailure as exc:
            AppHelper.callAfter(self._finish_failure, exc)
        except Exception as exc:  # noqa: BLE001 - show the failure in the popup
            logger.exception("conversion failed")
            AppHelper.callAfter(self._finish_failure, exc)
        else:
            try:
                copy_to_clipboard(result.markdown)
            except Exception as exc:  # noqa: BLE001 - clipboard failure
                logger.exception("clipboard write failed")
                AppHelper.callAfter(self._finish_failure, exc)
            else:
                AppHelper.callAfter(
                    self._finish_success, result.chars, result.tokens
                )

    @objc.python_method
    def _progress(self, done, total, source, details, error) -> None:
        AppHelper.callAfter(
            self._update_progress,
            done,
            total,
            source.name,
            details,
            error,
        )

    @objc.python_method
    def _work_progress(self, state) -> None:
        AppHelper.callAfter(
            self._update_work_progress,
            state.pages_done,
            state.pages_total,
            state.ocr_done,
            state.ocr_total,
            state.fraction,
        )

    @objc.python_method
    def _update_work_progress(
        self,
        pages_done: int,
        pages_total: int,
        ocr_done: int,
        ocr_total: int,
        fraction: float,
    ) -> None:
        self._set_indeterminate(False)
        self.bar.setDoubleValue_(fraction * 100.0)
        if pages_total:
            text = f"{pages_done}/{pages_total} pages"
            if ocr_total or ocr_done:
                text += f" + {ocr_done}/{ocr_total} OCR"
        else:
            text = "Starting…"
        self.status_label.setStringValue_(text)
        logger.info(
            "work progress: %d/%d pages + %d/%d OCR",
            pages_done,
            pages_total,
            ocr_done,
            ocr_total,
        )

    @objc.python_method
    def _update_progress(self, done, total, name, details, error) -> None:
        suffix = " (failed)" if error else ""
        self.detail_label.setStringValue_(f"({done}/{total}) {name}{suffix}")
        text = details or error or ""
        self.detail_label.setToolTip_(text)

    @objc.python_method
    def _finish_success(self, chars: int, tokens: int) -> None:
        self.busy = False
        self._set_indeterminate(False)
        self.bar.setDoubleValue_(100.0)
        self.status_label.setStringValue_("Copied to clipboard!")
        self.detail_label.setStringValue_(
            f"{chars:,} characters · {tokens:,} tokens"
        )
        self.close_button.setHidden_(False)
        if self.pending:
            self._close_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0, self, "startPending:", None, False
            )
        else:
            self._close_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.5, self, "closeAfterSuccess:", None, False
            )

    @objc.python_method
    def _finish_failure(self, exc: Exception) -> None:
        self.busy = False
        self._set_indeterminate(False)
        self.bar.setDoubleValue_(0.0)
        self.status_label.setStringValue_("Couldn't copy")
        if isinstance(exc, BatchFailure) and exc.errors:
            for failed_path, failed_error in exc.errors:
                logger.error("conversion failed: %s: %s", failed_path, failed_error)
            first_path, first_error = exc.errors[0]
            text = f"{first_path.name}: {first_error}"
            if len(exc.errors) > 1:
                text += f" (+{len(exc.errors) - 1} more)"
        else:
            logger.error("conversion failed: %s", exc)
            text = str(exc)
        self.detail_label.setStringValue_(text.replace("\n", " ")[:240])
        self.detail_label.setToolTip_(text)
        self.close_button.setHidden_(False)
        self._show()

    @objc.python_method
    def _fail_with_message(self, title: str, message: str) -> None:
        self.status_label.setStringValue_(title)
        self.detail_label.setStringValue_(message.replace("\n", " ")[:240])
        self.detail_label.setToolTip_(message)
        self._set_indeterminate(False)
        self.bar.setDoubleValue_(0.0)
        self.close_button.setHidden_(False)
        self._show()

    def startPending_(self, timer) -> None:
        self._close_timer = None
        pending = self.pending
        self.pending = None
        self.busy = False
        if pending:
            self.beginBatch_(pending)

    def closeAfterSuccess_(self, timer) -> None:
        self._close_timer = None
        self.window.close()
        NSApplication.sharedApplication().terminate_(None)

    def close_(self, sender) -> None:
        self.window.close()
        NSApplication.sharedApplication().terminate_(None)

    def windowWillClose_(self, notification) -> None:
        NSApplication.sharedApplication().terminate_(None)

    # -- onboarding / installers -----------------------------------------

    def showOnboarding_(self, quick_action_error: str | None) -> None:
        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Copy 4 AI is ready")
        text = (
            "In Finder, select DOCX, PDF, or PPTX files, then right-click → "
            "Quick Actions → Copy 4 AI.\n\n"
            "The app uses Apple Live Text."
        )
        if quick_action_error:
            text += f"\n\nCould not install the Finder action:\n{quick_action_error}"
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_("Done")
        alert.addButtonWithTitle_("Reinstall Finder Action")

        response = alert.runModal()
        if response == NSAlertSecondButtonReturn:
            self._install_quick_action()
        app.terminate_(None)

    def _install_quick_action(self) -> None:
        from . import quickaction

        try:
            path = quickaction.install()
        except Exception as exc:  # noqa: BLE001 - show in an alert
            self._simple_alert("Could not install Finder action", str(exc))
            return
        self._simple_alert(
            "Finder action installed",
            f"Right-click selected files → Quick Actions → Copy 4 AI.\n\n{path}",
        )

    @objc.python_method
    def _simple_alert(self, title: str, message: str) -> None:
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.runModal()


class AppDelegate(NSObject):
    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.controller = None
        self.initial_files: list[Path] = []
        self.pending_files: list[Path] = []
        self.engine = "livetext"
        self.use_ocr = True
        self.jobs = 1
        self.quick_action_error = None
        return self

    def applicationDidFinishLaunching_(self, notification) -> None:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        if str(Path(sys.executable).resolve()).startswith("/Volumes/"):
            self._warn_run_from_dmg()
            return

        self.controller = ProgressController.alloc().initWithOptions_(
            {
                "engine": self.engine,
                "use_ocr": self.use_ocr,
                "jobs": self.jobs,
            }
        )

        from . import quickaction

        for removed in quickaction.remove_legacy_cli_wrappers():
            logger.info("removed legacy app CLI wrapper: %s", removed)

        try:
            quickaction.install()
        except Exception as exc:  # noqa: BLE001 - surface in onboarding
            logger.exception("quick action install failed")
            self.quick_action_error = str(exc)

        files = self.pending_files + self.initial_files
        if files:
            self.controller.beginBatch_(files)
        else:
            self.controller.showOnboarding_(self.quick_action_error)

    @objc.python_method
    def _warn_run_from_dmg(self) -> None:
        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Drag Copy 4 AI to Applications")
        alert.setInformativeText_(
            "Copy 4 AI is running from the installer disk. "
            "Drag the app to Applications, then open it from there."
        )
        alert.addButtonWithTitle_("Quit")
        alert.runModal()
        app.terminate_(None)

    def application_openFiles_(self, app, filenames) -> None:
        paths = [Path(name) for name in filenames]
        if self.controller is not None:
            self.controller.beginBatch_(paths)
        else:
            self.pending_files.extend(paths)

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender) -> bool:
        return True


def run_gui(
    files: list[str | Path] | None = None,
    *,
    engine: str = "livetext",
    jobs: int | None = None,
) -> int:
    _configure_logging()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = AppDelegate.alloc().init()
    delegate.initial_files = [Path(path) for path in (files or [])]
    delegate.engine = engine
    delegate.use_ocr = engine != "none"
    delegate.jobs = jobs or min(4, os.cpu_count() or 1)
    app.setDelegate_(delegate)

    global _delegate
    _delegate = delegate

    app.run()
    return 0


main = run_gui
