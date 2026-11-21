import Foundation

public final class VectorRenderer {
    private let resources: CP4AIResources

    public init(resources: CP4AIResources) {
        self.resources = resources
    }

    public func svgToPNG(_ svg: URL, outPNG: URL, width: Int = 2400) -> Bool {
        guard let rsvg = resources.rsvgConvert else { return false }
        do {
            let output = try ProcessRunner.run(
                rsvg,
                [svg.path, "-o", outPNG.path, "--width", String(width)],
                environment: resources.environment()
            )
            let attributes = try? FileManager.default.attributesOfItem(atPath: outPNG.path)
            let size = (attributes?[.size] as? NSNumber)?.intValue ?? 0
            return output.succeeded && size > 0
        } catch {
            return false
        }
    }

    public func vectorToPNG(_ source: URL, outPNG: URL, workdir: URL) -> Bool {
        let suffix = source.pathExtension.lowercased()
        if suffix == "emf", EMFPlusExtractor.extract(emf: source, outPNG: outPNG) {
            return true
        }
        guard suffix == "emf" || suffix == "svg" else { return false }

        let svgPath = suffix == "svg"
            ? source
            : workdir.appendingPathComponent("\(source.deletingPathExtension().lastPathComponent)_vector.svg")

        if suffix == "emf" {
            guard let converter = resources.emf2svgConvert else { return false }
            do {
                let output = try ProcessRunner.run(
                    converter,
                    ["-p", "-i", source.path, "-o", svgPath.path],
                    environment: resources.environment()
                )
                guard output.succeeded,
                      FileManager.default.fileExists(atPath: svgPath.path),
                      let attributes = try? FileManager.default.attributesOfItem(atPath: svgPath.path),
                      ((attributes[.size] as? NSNumber)?.intValue ?? 0) >= 500 else {
                    return false
                }
                let text = (try? String(contentsOf: svgPath, encoding: .utf8)) ?? ""
                guard text.contains("<path") || text.contains("<image") || text.contains("<text") else {
                    return false
                }
            } catch {
                return false
            }
        }
        return svgToPNG(svgPath, outPNG: outPNG)
    }
}
