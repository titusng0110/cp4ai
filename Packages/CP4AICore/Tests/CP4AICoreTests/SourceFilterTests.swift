import XCTest
@testable import CP4AICore

final class SourceFilterTests: XCTestCase {
    func testFiltersUnsupportedAndDirectories() throws {
        let directory = try TemporaryDirectory(prefix: "cp4ai_filter_test_")
        let docx = directory.url.appendingPathComponent("a.docx")
        let pdf = directory.url.appendingPathComponent("b.pdf")
        let text = directory.url.appendingPathComponent("c.txt")
        let folder = directory.url.appendingPathComponent("folder")
        try Data().write(to: docx)
        try Data().write(to: pdf)
        try Data().write(to: text)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

        let (valid, rejected) = SourceFilter.filter([docx, pdf, text, folder])
        XCTAssertEqual(valid.map(\.lastPathComponent).sorted(), ["a.docx", "b.pdf"])
        XCTAssertEqual(Set(rejected.map(\.0.lastPathComponent)), ["c.txt", "folder"])
    }
}
