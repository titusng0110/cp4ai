import XCTest
@testable import CP4AICore

final class PptxPostProcessorTests: XCTestCase {
    private func processor(useOCR: Bool = false) -> PptxPostProcessor {
        let resources = CP4AIResources.locate()
        return PptxPostProcessor(
            mediaDir: URL(fileURLWithPath: NSTemporaryDirectory()),
            workdir: URL(fileURLWithPath: NSTemporaryDirectory()),
            ocr: OCRService(languages: ["en-US"]),
            cache: OCRCache(),
            renderer: VectorRenderer(resources: resources),
            useOCR: useOCR,
            onOCR: nil
        )
    }

    func testSplitSlides() {
        let (preamble, chunks) = processor().splitSlides("intro\n\n## A\n\ntext\n\n## B\n\nmore")
        XCTAssertEqual(preamble, "intro")
        XCTAssertEqual(chunks.count, 2)
        XCTAssertTrue(chunks[0].hasPrefix("## A"))
        XCTAssertTrue(chunks[1].hasPrefix("## B"))
    }

    func testMissingImageKeepsCoordinates() {
        let markdown = "![alt](missing.png \"Title\")"
        let output = processor().replaceImages(
            in: markdown,
            imageCoords: ["Title": (x: 25, y: 50, width: 50, height: 10)],
            slideWidth: 100,
            slideHeight: 100
        )
        XCTAssertTrue(output.contains("image not extracted: Title"))
        XCTAssertTrue(output.contains("[top: 50%, left: 30%, width: 50%, height: 10%]"))
    }

    func testAppendNotesAndComments() {
        var meta = PptxSlideMeta()
        meta.notes = "Speaker note"
        meta.comments = [PptxComment(author: "Alice", date: "2026-01-01", text: "A comment")]
        let output = processor().appendSlideMeta("## Slide", meta: meta)
        XCTAssertTrue(output.contains("### Speaker notes"))
        XCTAssertTrue(output.contains("> Speaker note"))
        XCTAssertTrue(output.contains("### Comments"))
        XCTAssertTrue(output.contains("> **Alice — 2026-01-01**"))
    }
}
