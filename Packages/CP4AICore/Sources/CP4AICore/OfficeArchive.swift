import Foundation

/// Extracts an OOXML zip into a temporary directory and exposes its parts.
public final class OfficeArchive {
    public let root: URL
    private let temporary: TemporaryDirectory

    public init(url: URL) throws {
        temporary = try TemporaryDirectory(prefix: "cp4ai_office_")
        root = temporary.url
        let output = try ProcessRunner.run(
            URL(fileURLWithPath: "/usr/bin/unzip"),
            ["-q", "-o", url.standardizedFileURL.path, "-d", root.path]
        )
        guard output.succeeded else {
            throw ConversionError.invalidDocument(
                "could not read \(url.lastPathComponent): \(output.stderr)"
            )
        }
    }

    public func data(at path: String) -> Data? {
        try? Data(contentsOf: root.appendingPathComponent(path))
    }

    public func exists(_ path: String) -> Bool {
        FileManager.default.fileExists(atPath: root.appendingPathComponent(path).path)
    }

    public func files(in directory: String) -> [String] {
        let target = root.appendingPathComponent(directory)
        guard let enumerator = FileManager.default.enumerator(
            at: target,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return []
        }
        var paths: [String] = []
        for case let file as URL in enumerator {
            guard (try? file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
                continue
            }
            if let relative = file.path.removingPrefix(target.path + "/") {
                paths.append(relative)
            }
        }
        return paths.sorted()
    }
}

extension String {
    public func removingPrefix(_ prefix: String) -> String? {
        guard hasPrefix(prefix) else { return nil }
        return String(dropFirst(prefix.count))
    }
}

public enum XMLTools {
    public static func document(_ data: Data) -> XMLDocument? {
        try? XMLDocument(data: data, options: [.nodePreserveWhitespace, .nodePreserveCDATA])
    }

    public static func elements(
        in node: XMLNode,
        localName: String,
        namespace: String? = nil
    ) -> [XMLElement] {
        var result: [XMLElement] = []
        for child in node.children ?? [] {
            guard let element = child as? XMLElement else { continue }
            if element.localName == localName,
               namespace == nil || element.uri == namespace {
                result.append(element)
            }
            result.append(contentsOf: elements(in: element, localName: localName, namespace: namespace))
        }
        return result
    }

    public static func descendants(_ element: XMLElement, localName: String, namespace: String? = nil) -> [XMLElement] {
        elements(in: element, localName: localName, namespace: namespace)
    }

    public static func attribute(
        _ element: XMLElement,
        _ name: String,
        namespace: String? = nil
    ) -> String? {
        for attribute in element.attributes ?? [] {
            if let namespace, attribute.uri != namespace { continue }
            if attribute.localName == name || attribute.name == name {
                return attribute.stringValue
            }
        }
        return nil
    }

    public static func text(of element: XMLElement, localName: String = "t", namespace: String? = nil) -> String {
        descendants(element, localName: localName, namespace: namespace)
            .compactMap(\.stringValue)
            .joined()
    }

    public static func paragraphs(_ document: XMLDocument, localName: String = "p", namespace: String? = nil) -> [XMLElement] {
        elements(in: document, localName: localName, namespace: namespace)
    }
}
