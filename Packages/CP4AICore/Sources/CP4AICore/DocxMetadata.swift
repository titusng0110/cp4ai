import Foundation

public struct DocxComment {
    public let id: String
    public let author: String
    public let date: String
    public let text: String
    public let anchor: String
}

public enum DocxMetadata {
    private static let wordNamespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    public static func header(at url: URL) -> String {
        guard let archive = try? OfficeArchive(url: url) else { return "" }
        let names = archive.files(in: "word")
            .filter { $0.range(of: #"^header\d+\.xml$"#, options: .regularExpression) != nil }
            .sorted()
        for name in names {
            guard let data = archive.data(at: "word/\(name)"),
                  let document = XMLTools.document(data) else {
                continue
            }
            let paragraphs = XMLTools.paragraphs(document, namespace: wordNamespace)
            let text = paragraphs
                .map { XMLTools.text(of: $0, namespace: wordNamespace) }
                .map { $0.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression) }
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .joined(separator: " ")
            let collapsed = text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !collapsed.isEmpty,
               collapsed.range(of: #"^PAGE(?:\s*\d+)?$"#, options: [.regularExpression, .caseInsensitive]) == nil {
                return collapsed
            }
        }
        return ""
    }

    public static func comments(at url: URL) -> [DocxComment] {
        guard let archive = try? OfficeArchive(url: url),
              let commentsData = archive.data(at: "word/comments.xml"),
              let documentData = archive.data(at: "word/document.xml"),
              let commentsDocument = XMLTools.document(commentsData),
              let document = XMLTools.document(documentData) else {
            return []
        }

        var anchors: [String: [String]] = [:]
        var order: [String] = []

        for paragraph in XMLTools.paragraphs(document, namespace: wordNamespace) {
            var ids: [String] = []
            for element in XMLTools.allElements(in: paragraph) {
                guard element.uri == wordNamespace else { continue }
                if element.localName == "commentRangeStart" || element.localName == "commentReference",
                   let id = XMLTools.attribute(element, "id") {
                    ids.append(id)
                }
            }
            guard !ids.isEmpty else { continue }
            let text = XMLTools.text(of: paragraph, namespace: wordNamespace)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            for id in ids {
                if !order.contains(id) { order.append(id) }
                if !text.isEmpty {
                    var list = anchors[id] ?? []
                    if !list.contains(text) { list.append(text) }
                    anchors[id] = list
                }
            }
        }

        var comments: [DocxComment] = []
        for element in XMLTools.elements(in: commentsDocument, localName: "comment", namespace: wordNamespace) {
            let id = XMLTools.attribute(element, "id") ?? ""
            let author = XMLTools.attribute(element, "author") ?? "Unknown"
            let date = String((XMLTools.attribute(element, "date") ?? "").prefix(10))
            var paragraphs: [String] = []
            for paragraph in XMLTools.elements(in: element, localName: "p", namespace: wordNamespace) {
                let text = XMLTools.text(of: paragraph, namespace: wordNamespace)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty { paragraphs.append(text) }
            }
            guard !paragraphs.isEmpty else { continue }
            comments.append(
                DocxComment(
                    id: id,
                    author: author,
                    date: date,
                    text: paragraphs.joined(separator: "\n\n"),
                    anchor: (anchors[id] ?? []).joined(separator: " … ")
                )
            )
        }

        let rank = Dictionary(uniqueKeysWithValues: order.enumerated().map { ($1, $0) })
        return comments.sorted { lhs, rhs in
            let left = rank[lhs.id] ?? Int.max
            let right = rank[rhs.id] ?? Int.max
            if left != right { return left < right }
            return lhs.id < rhs.id
        }
    }
}
