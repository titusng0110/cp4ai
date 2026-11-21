import Foundation

/// Exact `cl100k_base` token count, ported from tiktoken's BPE algorithm.
///
/// Only counts are needed, so the encoder does not retain token IDs.  The
/// vocabulary file is the same `cl100k_base.tiktoken` data tiktoken uses.
public final class TokenCounter {
    private static let pattern = #"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"#

    private var ranks: [Data: Int] = [:]
    private let regex: NSRegularExpression

    public init(vocabURL: URL) throws {
        guard let text = try? String(contentsOf: vocabURL, encoding: .utf8) else {
            throw ConversionError.invalidDocument("could not read tokenizer vocabulary: \(vocabURL.path)")
        }
        for line in text.split(separator: "\n") {
            let fields = line.split(separator: " ", maxSplits: 1)
            guard fields.count == 2,
                  let data = Data(base64Encoded: String(fields[0])),
                  let rank = Int(fields[1]) else {
                continue
            }
            ranks[data] = rank
        }
        guard !ranks.isEmpty else {
            throw ConversionError.invalidDocument("tokenizer vocabulary is empty: \(vocabURL.path)")
        }
        guard let regex = try? NSRegularExpression(pattern: Self.pattern) else {
            throw ConversionError.invalidDocument("could not compile tokenizer pattern")
        }
        self.regex = regex
    }

    public func count(_ text: String) -> Int {
        guard !text.isEmpty else { return 0 }
        let ns = text as NSString
        let matches = regex.matches(in: text, range: NSRange(location: 0, length: ns.length))
        guard !matches.isEmpty else { return 0 }
        var total = 0
        for match in matches {
            total += encode(ns.substring(with: match.range))
        }
        return total
    }

    private func encode(_ piece: String) -> Int {
        let bytes = Array(piece.utf8)
        guard !bytes.isEmpty else { return 0 }
        var parts = bytes.map { [$0] }

        while parts.count > 1 {
            var minimumRank = Int.max
            for index in 0..<(parts.count - 1) {
                let pair = Data(parts[index] + parts[index + 1])
                if let rank = ranks[pair], rank < minimumRank {
                    minimumRank = rank
                }
            }
            guard minimumRank != Int.max else { break }

            var merged: [[UInt8]] = []
            merged.reserveCapacity(parts.count)
            var index = 0
            var changed = false
            while index < parts.count {
                if index + 1 < parts.count,
                   ranks[Data(parts[index] + parts[index + 1])] == minimumRank {
                    merged.append(parts[index] + parts[index + 1])
                    index += 2
                    changed = true
                } else {
                    merged.append(parts[index])
                    index += 1
                }
            }
            if !changed { break }
            parts = merged
        }
        return parts.count
    }
}
