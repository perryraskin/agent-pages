import Foundation

@main struct ReferenceChecks {
    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let file = root.appendingPathComponent("test.hermespage")
        let good = PageReference(pageID: "fleet-health", title: "Fleet health")
        try JSONEncoder().encode(good).write(to: file)
        let decoded = try PageReference.read(file)
        precondition(decoded == good)
        for text in [
            "{\"version\":2,\"pageID\":\"fleet-health\",\"title\":\"Test\"}",
            "{\"version\":1,\"pageID\":\"../../secret\",\"title\":\"Test\"}",
            "{\"version\":1,\"pageID\":\"https://evil\",\"title\":\"Test\"}",
            "not JSON", String(repeating: "x", count: PageReference.maximumBytes + 1)
        ] {
            try Data(text.utf8).write(to: file)
            do { _ = try PageReference.read(file); fatalError("Accepted invalid reference") } catch { }
        }
        let snapshot = PageReference(pageID: "fleet-health", title: "Fleet health", html: "<html><head></head><body>Page</body></html>")
        try JSONEncoder().encode(snapshot).write(to: file)
        let decodedSnapshot = try PageReference.read(file)
        precondition(decodedSnapshot == snapshot)
        let isolated = PageReference.isolatedHTML(snapshot.html!)
        precondition(isolated.contains("connect-src 'none'"))
        precondition(isolated.contains("base-uri 'none'"))
        print("PASS: live-reference decoding, version checks, path/URL rejection, malformed and oversized input")
    }
}
