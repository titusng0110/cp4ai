import Foundation

public enum TextTools {
    private static let ligatures: [Character: String] = [
        "\u{FB00}": "ff",
        "\u{FB01}": "fi",
        "\u{FB02}": "fl",
        "\u{FB03}": "ffi",
        "\u{FB04}": "ffl",
    ]

    public static func clean(_ text: String) -> String {
        var value = String(text.map { ligatures[$0] ?? String($0) }.joined())
        value = value.replacingOccurrences(of: "\u{00A0}", with: " ")
        value = value.replacingOccurrences(of: "\u{00AD}", with: "")
        value = value.replacingOccurrences(
            of: "(?<=\\d)\\s*\\[(st|nd|rd|th)\\]",
            with: "$1",
            options: [.regularExpression, .caseInsensitive]
        )

        let lines = value.components(separatedBy: "\n").map { line -> String in
            var cleaned = line
            while cleaned.hasSuffix("\r") || cleaned.hasSuffix(" ") || cleaned.hasSuffix("\t") {
                cleaned.removeLast()
            }
            return cleaned
        }
        value = lines.joined(separator: "\n")
        value = value.replacingOccurrences(
            of: "\n{3,}",
            with: "\n\n",
            options: .regularExpression
        )
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public static func yamlValue(_ value: String) -> String {
        var output = "\""
        for scalar in value.unicodeScalars {
            switch scalar {
            case "\"":
                output += "\\\""
            case "\\":
                output += "\\\\"
            case "\n":
                output += "\\n"
            case "\r":
                output += "\\r"
            case "\t":
                output += "\\t"
            case "\u{08}":
                output += "\\b"
            case "\u{0C}":
                output += "\\f"
            default:
                if scalar.value < 0x20 {
                    output += String(format: "\\u%04x", scalar.value)
                } else {
                    output.unicodeScalars.append(scalar)
                }
            }
        }
        return output + "\""
    }

    public static func title(of url: URL) -> String {
        url.deletingPathExtension().lastPathComponent
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public static func displayPath(_ url: URL) -> String {
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).standardizedFileURL.path
        let resolved = url.standardizedFileURL.path
        if cwd != "/", resolved == cwd {
            return "."
        }
        if cwd != "/", resolved.hasPrefix(cwd + "/") {
            return String(resolved.dropFirst(cwd.count + 1))
        }
        return resolved
    }

    public static func frontMatter(
        path: URL,
        format: String,
        extras: [(String, String?)]
    ) -> String {
        var lines = [
            "---",
            "source: \(yamlValue(displayPath(path)))",
            "format: \(format)",
            "converted: \(yamlValue(today()))",
        ]
        for (key, value) in extras {
            guard let value, !value.isEmpty else { continue }
            lines.append("\(key): \(yamlValue(value))")
        }
        lines.append("---")
        return lines.joined(separator: "\n")
    }

    public static func today() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    public static func writeMarkdown(_ body: String, to url: URL) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let cleaned = body.trimmingCharacters(in: .whitespacesAndNewlines)
        try (cleaned + "\n").write(to: url, atomically: true, encoding: .utf8)
    }

    public static func tokenSet(_ text: String) -> Set<String> {
        guard let regex = try? NSRegularExpression(pattern: "[a-z0-9]{2,}") else { return [] }
        let ns = text.lowercased() as NSString
        let matches = regex.matches(in: text.lowercased(), range: NSRange(location: 0, length: ns.length))
        return Set(matches.map { ns.substring(with: $0.range) })
    }

    public static func usefulOCR(_ text: String) -> Bool {
        text.replacingOccurrences(of: "\\s+", with: "", options: .regularExpression).count >= 10
    }

    /// True when `candidate` appears in `text` in order after all Unicode
    /// whitespace is removed from both strings.
    ///
    /// This is deliberately exact: case, punctuation and duplicate characters
    /// matter. It is used to drop OCR only when the recognized image text is
    /// already present, in order, in the same page's native text layer.
    public static func isOrderedSubsequenceAfterStrippingWhitespace(
        _ candidate: String,
        of text: String
    ) -> Bool {
        let needle = candidate.filter { !$0.isWhitespace }
        guard !needle.isEmpty else { return true }

        var index = needle.startIndex
        for character in text where !character.isWhitespace {
            if character == needle[index] {
                index = needle.index(after: index)
                if index == needle.endIndex { return true }
            }
        }
        return false
    }

    public static func htmlEscape(_ text: String) -> String {
        text
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&#x27;")
    }

    public static func htmlUnescape(_ text: String) -> String {
        var value = text
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&apos;", with: "'")
            .replacingOccurrences(of: "&amp;", with: "&")
        let pattern = "&#(x?)([0-9A-Fa-f]+);"
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return value }
        let matches = regex.matches(in: value, range: NSRange(location: 0, length: (value as NSString).length))
        for match in matches.reversed() {
            let ns = value as NSString
            let hexFlag = ns.substring(with: match.range(at: 1))
            let digits = ns.substring(with: match.range(at: 2))
            let radix = hexFlag.isEmpty ? 10 : 16
            guard let code = UInt32(digits, radix: radix), let scalar = UnicodeScalar(code) else { continue }
            value = ns.replacingCharacters(in: match.range, with: String(scalar))
        }
        return value
    }

    public static func naturalCompare(_ lhs: String, _ rhs: String) -> Bool {
        let left = naturalParts(lhs)
        let right = naturalParts(rhs)
        for (a, b) in zip(left, right) {
            if a == b { continue }
            switch (a, b) {
            case let (.number(x), .number(y)):
                if x != y { return x < y }
            case let (.text(x), .text(y)):
                let result = x.localizedCaseInsensitiveCompare(y)
                if result != .orderedSame { return result == .orderedAscending }
            case (.number, .text):
                return true
            case (.text, .number):
                return false
            }
        }
        return left.count < right.count
    }

    private enum NaturalPart: Equatable {
        case number(Int)
        case text(String)
    }

    private static func naturalParts(_ value: String) -> [NaturalPart] {
        var parts: [NaturalPart] = []
        var current = ""
        var currentIsNumber = false

        func flush() {
            guard !current.isEmpty else { return }
            if currentIsNumber, let number = Int(current) {
                parts.append(.number(number))
            } else {
                parts.append(.text(current.lowercased()))
            }
            current = ""
        }

        for character in value {
            let isNumber = character.isNumber
            if !current.isEmpty, isNumber != currentIsNumber {
                flush()
            }
            currentIsNumber = isNumber
            current.append(character)
        }
        flush()
        return parts
    }
}

public enum RegexTools {
    public static func compile(
        _ pattern: String,
        options: NSRegularExpression.Options = []
    ) -> NSRegularExpression? {
        try? NSRegularExpression(pattern: pattern, options: options)
    }

    public static func replacingMatches(
        in text: String,
        regex: NSRegularExpression,
        transform: (NSTextCheckingResult, NSString) -> String
    ) -> String {
        let ns = text as NSString
        let matches = regex.matches(in: text, range: NSRange(location: 0, length: ns.length))
        guard !matches.isEmpty else { return text }

        var output = ""
        var last = 0
        for match in matches {
            if match.range.location > last {
                output += ns.substring(with: NSRange(location: last, length: match.range.location - last))
            }
            output += transform(match, ns)
            last = match.range.location + match.range.length
        }
        if last < ns.length {
            output += ns.substring(from: last)
        }
        return output
    }

    public static func lineContext(in text: NSString, around range: NSRange) -> (line: String, start: Int, end: Int) {
        var start = 0
        if range.location > 0 {
            let previous = text.range(of: "\n", options: .backwards, range: NSRange(location: 0, length: range.location))
            if previous.location != NSNotFound {
                start = previous.location + previous.length
            }
        }
        var end = text.length
        let next = text.range(of: "\n", options: [], range: NSRange(location: range.location, length: text.length - range.location))
        if next.location != NSNotFound {
            end = next.location
        }
        return (text.substring(with: NSRange(location: start, length: end - start)), start, end)
    }
}
