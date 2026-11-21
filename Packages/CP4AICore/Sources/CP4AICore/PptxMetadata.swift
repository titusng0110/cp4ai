import Foundation

public struct PptxComment {
    public let author: String
    public let date: String
    public let text: String
}

public struct PptxSlideMeta {
    public var notes: String = ""
    public var comments: [PptxComment] = []
    public var images: [String: (x: Int, y: Int, width: Int, height: Int)] = [:]
    public var width: Int = 0
    public var height: Int = 0
}

public enum PptxMetadata {
    private static let pNamespace = "http://schemas.openxmlformats.org/presentationml/2006/main"
    private static let aNamespace = "http://schemas.openxmlformats.org/drawingml/2006/main"
    private static let rNamespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    private static let relNamespace = "http://schemas.openxmlformats.org/package/2006/relationships"

    public static func slides(at url: URL) -> [PptxSlideMeta] {
        guard let archive = try? OfficeArchive(url: url),
              let presentationData = archive.data(at: "ppt/presentation.xml"),
              let presentation = XMLTools.document(presentationData) else {
            return []
        }

        let relationships = rels(archive: archive, part: "ppt/presentation.xml")
        var slideParts: [String] = []
        for slideID in XMLTools.elements(in: presentation, localName: "sldId", namespace: pNamespace) {
            guard let relID = XMLTools.attribute(slideID, "id", namespace: rNamespace),
                  let relationship = relationships[relID] else {
                continue
            }
            slideParts.append(relationship.target)
        }

        let (slideWidth, slideHeight) = slideSize(presentation)
        let authors = commentAuthors(archive: archive)
        return slideParts.map { part in
            var meta = PptxSlideMeta()
            meta.width = slideWidth
            meta.height = slideHeight
            meta.notes = notesText(archive: archive, slidePart: part)
            meta.comments = comments(archive: archive, slidePart: part, authors: authors)
            meta.images = images(archive: archive, slidePart: part, relationships: rels(archive: archive, part: part))
            return meta
        }
    }

    public static func slideCount(at url: URL) -> Int {
        slides(at: url).count
    }

    public static func pictureCount(at url: URL) -> Int {
        slides(at: url).reduce(0) { $0 + $1.images.count }
    }

    private static func rels(
        archive: OfficeArchive,
        part: String
    ) -> [String: (type: String, target: String)] {
        let directory = (part as NSString).deletingLastPathComponent
        let filename = (part as NSString).lastPathComponent
        let relsPath = directory.isEmpty
            ? "_rels/\(filename).rels"
            : "\(directory)/_rels/\(filename).rels"
        guard let data = archive.data(at: relsPath),
              let document = XMLTools.document(data) else {
            return [:]
        }
        var result: [String: (String, String)] = [:]
        for relationship in XMLTools.elements(in: document, localName: "Relationship", namespace: relNamespace) {
            guard let id = XMLTools.attribute(relationship, "Id"),
                  let target = XMLTools.attribute(relationship, "Target") else {
                continue
            }
            let type = XMLTools.attribute(relationship, "Type") ?? ""
            result[id] = (type, packagePath(base: part, target: target))
        }
        return result
    }

    private static func slideSize(_ presentation: XMLDocument) -> (Int, Int) {
        guard let size = XMLTools.elements(in: presentation, localName: "sldSz", namespace: pNamespace).first,
              let width = Int(XMLTools.attribute(size, "cx") ?? "0"),
              let height = Int(XMLTools.attribute(size, "cy") ?? "0") else {
            return (0, 0)
        }
        return (width, height)
    }

    private static func commentAuthors(archive: OfficeArchive) -> [String: String] {
        guard let data = archive.data(at: "ppt/commentAuthors.xml"),
              let document = XMLTools.document(data) else {
            return [:]
        }
        var authors: [String: String] = [:]
        for author in XMLTools.elements(in: document, localName: "cmAuthor", namespace: pNamespace) {
            let id = XMLTools.attribute(author, "id") ?? ""
            authors[id] = XMLTools.attribute(author, "name") ?? "Unknown"
        }
        return authors
    }

    private static func notesText(archive: OfficeArchive, slidePart: String) -> String {
        let relationships = rels(archive: archive, part: slidePart)
        guard let notesPart = relationships.values.first(where: { $0.type.hasSuffix("/notesSlide") })?.target,
              let data = archive.data(at: notesPart),
              let document = XMLTools.document(data) else {
            return ""
        }
        var lines: [String] = []
        for shape in XMLTools.elements(in: document, localName: "sp", namespace: pNamespace) {
            if let placeholder = XMLTools.elements(in: shape, localName: "ph", namespace: pNamespace).first,
               XMLTools.attribute(placeholder, "type") != "body" {
                continue
            }
            guard let body = XMLTools.elements(in: shape, localName: "txBody", namespace: pNamespace).first else {
                continue
            }
            for paragraph in XMLTools.elements(in: body, localName: "p", namespace: aNamespace) {
                let text = XMLTools.text(of: paragraph, namespace: aNamespace)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty { lines.append(text) }
            }
        }
        let notes = lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        return notes == "-" || notes == "Click to add notes" ? "" : notes
    }

    private static func comments(
        archive: OfficeArchive,
        slidePart: String,
        authors: [String: String]
    ) -> [PptxComment] {
        let relationships = rels(archive: archive, part: slidePart)
        guard let commentsPart = relationships.values.first(where: { $0.type.hasSuffix("/comments") })?.target,
              let data = archive.data(at: commentsPart),
              let document = XMLTools.document(data) else {
            return []
        }
        var result: [PptxComment] = []
        for comment in XMLTools.elements(in: document, localName: "cm", namespace: pNamespace) {
            var text = ""
            if let textElement = XMLTools.elements(in: comment, localName: "text", namespace: pNamespace).first {
                text = textElement.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            } else {
                text = XMLTools.text(of: comment, namespace: aNamespace)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if text.isEmpty { continue }
            result.append(
                PptxComment(
                    author: authors[XMLTools.attribute(comment, "authorId") ?? ""] ?? "Unknown",
                    date: String((XMLTools.attribute(comment, "dt") ?? "").prefix(10)),
                    text: text
                )
            )
        }
        return result
    }

    private static func images(
        archive: OfficeArchive,
        slidePart: String,
        relationships: [String: (type: String, target: String)]
    ) -> [String: (Int, Int, Int, Int)] {
        guard let data = archive.data(at: slidePart),
              let document = XMLTools.document(data) else {
            return [:]
        }
        var result: [String: (Int, Int, Int, Int)] = [:]
        for picture in XMLTools.elements(in: document, localName: "pic", namespace: pNamespace) {
            guard let transform = XMLTools.elements(in: picture, localName: "xfrm", namespace: aNamespace).first,
                  let offset = XMLTools.elements(in: transform, localName: "off", namespace: aNamespace).first,
                  let extent = XMLTools.elements(in: transform, localName: "ext", namespace: aNamespace).first,
                  let x = Int(XMLTools.attribute(offset, "x") ?? "0"),
                  let y = Int(XMLTools.attribute(offset, "y") ?? "0"),
                  let width = Int(XMLTools.attribute(extent, "cx") ?? "0"),
                  let height = Int(XMLTools.attribute(extent, "cy") ?? "0") else {
                continue
            }
            if let nameElement = XMLTools.elements(in: picture, localName: "cNvPr", namespace: pNamespace).first,
               let name = XMLTools.attribute(nameElement, "name"), !name.isEmpty {
                result[name] = (x, y, width, height)
            }
            if let blip = XMLTools.elements(in: picture, localName: "blip", namespace: aNamespace).first,
               let relID = XMLTools.attribute(blip, "embed", namespace: rNamespace),
               let relationship = relationships[relID] {
                let basename = (relationship.target as NSString).lastPathComponent
                result[basename] = (x, y, width, height)
            }
        }
        return result
    }

    private static func packagePath(base: String, target: String) -> String {
        if target.hasPrefix("/") { return String(target.dropFirst()) }
        let directory = (base as NSString).deletingLastPathComponent
        let joined = directory.isEmpty ? target : "\(directory)/\(target)"
        var stack: [String] = []
        for component in joined.split(separator: "/") {
            switch component {
            case ".":
                continue
            case "..":
                if !stack.isEmpty { stack.removeLast() }
            default:
                stack.append(String(component))
            }
        }
        return stack.joined(separator: "/")
    }
}
