import XCTest
@testable import CP4AICore

final class TextToolsTests: XCTestCase {
    func testCleanRepairsTypography() {
        let input = "ﬁle\u{00A0}name soft\u{00AD}hyphen 1 [st] loan  \n\n\n\nnext"
        let cleaned = TextTools.clean(input)
        XCTAssertEqual(cleaned, "file name softhyphen 1st loan\n\nnext")
    }

    func testYAMLValueMatchesJSONString() {
        XCTAssertEqual(TextTools.yamlValue("a \"quote\" and \\ slash"), "\"a \\\"quote\\\" and \\\\ slash\"")
        XCTAssertEqual(TextTools.yamlValue("line\nbreak"), "\"line\\nbreak\"")
    }

    func testTokenSetAndUsefulOCR() {
        XCTAssertEqual(TextTools.tokenSet("Copy 4 AI, copy!"), ["copy", "ai"])
        XCTAssertTrue(TextTools.usefulOCR("1234567890"))
        XCTAssertFalse(TextTools.usefulOCR("12345"))
    }

    func testHTMLUnescape() {
        XCTAssertEqual(TextTools.htmlUnescape("a &amp; b &lt;c&gt; &#65; &#x42;"), "a & b <c> A B")
    }

    func testNaturalCompare() {
        let names = ["slide10", "slide2", "slide1"]
        XCTAssertEqual(names.sorted { TextTools.naturalCompare($0, $1) }, ["slide1", "slide2", "slide10"])
    }
}
