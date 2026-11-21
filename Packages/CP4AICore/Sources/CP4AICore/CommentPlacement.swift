import Foundation

public enum CommentPlacement {
    private static let spanPattern = #"<span[^>]*class="comment-(?:start|end|reference)"[^>]*\bid="(\d+)""#
    private static let listItemPattern = #"^[ \t]*(?:[-*+]|\d+[.)])\s+"#
    private static let leadingPattern = #"^[ \t]*"#

    public static func heading(_ comment: DocxComment, index: Int) -> String {
        var heading = "Comment \(index) — \(comment.author)"
        if !comment.date.isEmpty {
            heading += " — \(comment.date)"
        }
        return heading
    }

    public static func insert(
        markdown: String,
        comments: [DocxComment]
    ) -> (markdown: String, unplaced: [(Int, DocxComment)]) {
        guard !comments.isEmpty else { return (markdown, []) }
        guard let regex = RegexTools.compile(spanPattern) else { return (markdown, []) }

        let byID = Dictionary(uniqueKeysWithValues: comments.map { ($0.id, $0) })
        var number: [String: Int] = [:]
        for (index, comment) in comments.enumerated() {
            number[comment.id] = index + 1
        }

        let lines = markdown.components(separatedBy: "\n")
        let ns = markdown as NSString
        var lastLine: [String: Int] = [:]
        var lineIsTable: [Bool] = []
        var inHTMLTable = false

        var lineStart = 0
        for (lineIndex, line) in lines.enumerated() {
            if line.contains("<table") { inHTMLTable = true }
            lineIsTable.append(inHTMLTable || line.trimmingCharacters(in: .whitespaces).hasPrefix("|"))
            if !line.isEmpty {
                let lineRange = NSRange(location: lineStart, length: (line as NSString).length)
                for match in regex.matches(in: markdown, range: lineRange) {
                    let id = ns.substring(with: match.range(at: 1))
                    if byID[id] != nil { lastLine[id] = lineIndex }
                }
            }
            if line.contains("</table>") { inHTMLTable = false }
            lineStart += (line as NSString).length + 1
        }

        var insertions: [Int: [String]] = [:]
        var unplaced: [(Int, DocxComment)] = []
        for comment in comments {
            if let lineIndex = lastLine[comment.id] {
                insertions[lineIndex, default: []].append(comment.id)
            } else if let index = number[comment.id] {
                unplaced.append((index, comment))
            }
        }

        var output: [String] = []
        for (lineIndex, line) in lines.enumerated() {
            guard let ids = insertions[lineIndex], !ids.isEmpty else {
                output.append(line)
                continue
            }
            if lineIsTable[lineIndex] {
                var updated = line
                let pipeTable = updated.trimmingCharacters(in: .whitespaces).hasPrefix("|")
                for id in ids {
                    guard let comment = byID[id], let index = number[id] else { continue }
                    updated = placeInline(
                        line: updated,
                        commentID: id,
                        inline: inlineComment(comment, index: index, pipeTable: pipeTable),
                        pipeTable: pipeTable
                    )
                }
                output.append(updated)
                continue
            }

            output.append(line)
            var indent = leadingWhitespace(line)
            if line.range(of: listItemPattern, options: .regularExpression) != nil {
                indent += "    "
            }
            for id in ids {
                guard let comment = byID[id], let index = number[id] else { continue }
                output.append(contentsOf: commentBlock(comment, index: index, indent: indent))
            }
            output.append("")
        }

        return (output.joined(separator: "\n"), unplaced)
    }

    public static func appendix(_ comments: [(Int, DocxComment)]) -> String {
        guard !comments.isEmpty else { return "" }
        var output = [
            "---",
            "",
            "## Appendix: Comments not anchored in the body",
            "",
            "> These comments had no visible anchor in the converted Markdown, so they are reproduced verbatim below with their author, date and the passage Word recorded.",
        ]
        for (index, comment) in comments {
            output.append("")
            output.append("### \(heading(comment, index: index))")
            output.append("")
            let anchor = truncated(comment.anchor, limit: 400)
            if !anchor.isEmpty {
                output.append("**Attached to:** “\(anchor)”")
                output.append("")
            }
            output.append(
                comment.text.components(separatedBy: "\n")
                    .map { $0.trimmingCharacters(in: .whitespaces).isEmpty ? ">" : "> \($0)" }
                    .joined(separator: "\n")
            )
        }
        return output.joined(separator: "\n")
    }

    private static func commentBlock(_ comment: DocxComment, index: Int, indent: String) -> [String] {
        var lines = ["\(indent)> **\(heading(comment, index: index))**", "\(indent)>"]
        let anchor = truncated(comment.anchor, limit: 400)
        if !anchor.isEmpty {
            lines.append("\(indent)> **Attached to:** “\(anchor)”")
            lines.append("\(indent)>")
        }
        for line in comment.text.components(separatedBy: "\n") {
            lines.append(line.trimmingCharacters(in: .whitespaces).isEmpty ? "\(indent)>" : "\(indent)> \(line)")
        }
        return lines
    }

    private static func inlineComment(_ comment: DocxComment, index: Int, pipeTable: Bool) -> String {
        let text = comment.text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        var parts = ["<br><strong>\(heading(comment, index: index))</strong>"]
        let anchor = truncated(comment.anchor, limit: 200)
        if !anchor.isEmpty {
            parts.append(" <em>“\(TextTools.htmlEscape(anchor))”</em>")
        }
        parts.append(": \(TextTools.htmlEscape(text))")
        let inline = parts.joined()
        return pipeTable ? inline.replacingOccurrences(of: "|", with: "\\|") : inline
    }

    private static func placeInline(line: String, commentID: String, inline: String, pipeTable: Bool) -> String {
        guard let regex = RegexTools.compile(spanPattern) else { return line + inline }
        let ns = line as NSString
        let matches = regex.matches(in: line, range: NSRange(location: 0, length: ns.length))
            .filter { ns.substring(with: $0.range(at: 1)) == commentID }
        guard let last = matches.last else { return line + inline }
        let position = last.range.location

        if pipeTable {
            var index = position
            while index < ns.length {
                if ns.character(at: index) == 0x7C {
                    let previous = index > 0 ? ns.character(at: index - 1) : 0
                    if previous != 0x5C {
                        return ns.replacingCharacters(
                            in: NSRange(location: index, length: 0),
                            with: inline
                        )
                    }
                }
                index += 1
            }
            return line + inline
        }

        for closing in ["</td>", "</th>"] {
            let range = ns.range(of: closing, options: [], range: NSRange(location: position, length: ns.length - position))
            if range.location != NSNotFound {
                return ns.replacingCharacters(in: NSRange(location: range.location, length: 0), with: inline)
            }
        }
        return line + inline
    }

    private static func leadingWhitespace(_ line: String) -> String {
        guard let regex = RegexTools.compile(leadingPattern),
              let match = regex.firstMatch(in: line, range: NSRange(location: 0, length: (line as NSString).length)) else {
            return ""
        }
        return (line as NSString).substring(with: match.range)
    }

    private static func truncated(_ value: String, limit: Int) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > limit else { return trimmed }
        return String(trimmed.prefix(limit)).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
    }
}
