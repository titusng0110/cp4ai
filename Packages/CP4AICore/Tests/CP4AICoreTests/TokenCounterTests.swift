import XCTest
@testable import CP4AICore

final class TokenCounterTests: XCTestCase {
    func testKnownCounts() throws {
        let resources = CP4AIResources.locate()
        guard let vocab = resources.tokenizer else {
            throw XCTSkip("cl100k_base tokenizer data is not available")
        }
        let counter = try TokenCounter(vocabURL: vocab)
        let samples: [(String, Int)] = [
            ("", 0),
            ("hello world", 2),
            ("Copy 4 AI", 4),
            ("Line one\nLine two\n\nLine three", 8),
            ("The quick brown fox jumps over the lazy dog.", 10),
            ("Unicode: café — “quotes” … 中文", 10),
            ("The Vendor shall indemnify the Purchaser against all losses, claims, damages and expenses arising out of any breach of the warranties given in this Agreement.", 30),
            (String(repeating: "A", count: 1000), 125),
        ]
        for (text, expected) in samples {
            XCTAssertEqual(counter.count(text), expected, "token count for \(text.prefix(30))")
        }
    }
}
