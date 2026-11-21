import CryptoKit
import Foundation
import ImageIO
import Vision

public final class OCRService {
    public let languages: [String]

    public init(languages: [String]) {
        self.languages = languages.isEmpty ? ["en-US"] : languages
    }

    public var label: String {
        "Apple Vision (\(languages.joined(separator: ", ")))"
    }

    /// Synchronous entry point used by the worker queue.
    public func recognize(imageAt url: URL) throws -> String {
        let semaphore = DispatchSemaphore(value: 0)
        var outcome: Result<String, Error> = .success("")
        Task.detached {
            do {
                outcome = .success(try await self.recognizeAsync(imageAt: url))
            } catch {
                outcome = .failure(error)
            }
            semaphore.signal()
        }
        semaphore.wait()
        return try outcome.get()
    }

    /// Apple's current Swift Vision OCR API (macOS 15+), revision 3.
    public func recognizeAsync(imageAt url: URL) async throws -> String {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            return ""
        }
        let flattened = Self.flatten(image)

        var request = RecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = languages.map { Locale.Language(identifier: $0) }

        let handler = ImageRequestHandler(flattened)
        let observations = try await handler.perform(request)

        var rows: [(maxY: Double, minX: Double, text: String)] = []
        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let box = observation.boundingBox.cgRect
            rows.append((Double(box.maxY), Double(box.minX), candidate.string))
        }
        rows.sort { left, right in
            if abs(left.maxY - right.maxY) > 0.005 {
                return left.maxY > right.maxY
            }
            return left.minX < right.minX
        }

        return rows.map(\.text)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Live Text ignores transparent backgrounds; flatten onto white first.
    private static func flatten(_ image: CGImage) -> CGImage {
        let width = image.width
        let height = image.height
        guard width > 0, height > 0,
              let context = CGContext(
                data: nil,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
              ) else {
            return image
        }
        context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return context.makeImage() ?? image
    }
}

public final class OCRCache {
    private var storage: [String: String] = [:]
    private let lock = NSLock()

    public init() {}

    public func text(for key: String) -> String? {
        lock.lock()
        defer { lock.unlock() }
        return storage[key]
    }

    public func store(_ text: String, for key: String) {
        lock.lock()
        storage[key] = text
        lock.unlock()
    }

    public static func digest(of url: URL) -> String {
        guard let data = try? Data(contentsOf: url) else { return url.path }
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}
