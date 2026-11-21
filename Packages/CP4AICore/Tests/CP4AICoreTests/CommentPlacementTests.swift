import XCTest
@testable import CP4AICore

final class CommentPlacementTests: XCTestCase {
    private func comment(id: String, text: String, anchor: String) -> DocxComment {
        DocxComment(id: id, author: "Alice", date: "2026-01-01", text: text, anchor: anchor)
    }

    func testInlinePlacementAfterParagraph() {
        let markdown = "Before <span class=\"comment-start\" id=\"0\">anchored</span> after.\n\nNext."
        let result = CommentPlacement.insert(
            markdown: markdown,
            comments: [comment(id: "0", text: "A note", anchor: "anchored")]
        )
        XCTAssertTrue(result.markdown.contains("> **Comment 1 — Alice — 2026-01-01**"))
        XCTAssertTrue(result.markdown.contains("> A note"))
        XCTAssertTrue(result.unplaced.isEmpty)
    }

    func testTablePlacementStaysInCell() {
        let markdown = "| <span class=\"comment-start\" id=\"1\">cell</span> | other |\n"
        let result = CommentPlacement.insert(
            markdown: markdown,
            comments: [comment(id: "1", text: "Cell note", anchor: "cell")]
        )
        XCTAssertTrue(result.markdown.contains("<br><strong>Comment 1 — Alice — 2026-01-01</strong>"))
        XCTAssertTrue(result.markdown.contains("Cell note"))
        XCTAssertFalse(result.markdown.contains("\n> "))
    }

    func testUnplacedCommentGoesToAppendix() {
        let result = CommentPlacement.insert(
            markdown: "Nothing here.",
            comments: [comment(id: "9", text: "Lost", anchor: "missing")]
        )
        XCTAssertEqual(result.unplaced.count, 1)
        let appendix = CommentPlacement.appendix(result.unplaced)
        XCTAssertTrue(appendix.contains("## Appendix: Comments not anchored in the body"))
        XCTAssertTrue(appendix.contains("### Comment 1 — Alice — 2026-01-01"))
        XCTAssertTrue(appendix.contains("> Lost"))
    }
}
