import XCTest
@testable import CP4AICore

final class PlaceholderTests: XCTestCase {
    func testVersion() {
        XCTAssertFalse(CP4AIVersion.current.isEmpty)
    }
}
