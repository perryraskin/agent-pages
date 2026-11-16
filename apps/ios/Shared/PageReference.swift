import Foundation

/// v1: legacy private live reference. v2: self-contained, network-isolated Page snapshot.
/// Incoming documents cannot choose a server or an arbitrary URL.
struct PageReference: Codable, Equatable, Identifiable {
    var id: String { "\(version)-\(pageID)" }
    let version: Int
    let pageID: String
    let title: String
    let html: String?
    static let contentType = "com.perryraskin.hermes-page"
    static let maximumBytes = 2_000_000
    init(pageID: String, title: String, html: String? = nil) {
        self.version = html == nil ? 1 : 2
        self.pageID = pageID; self.title = title; self.html = html
    }
    static func isValidID(_ id: String) -> Bool {
        id.range(of: "^[a-z0-9][a-z0-9-]{0,120}$", options: .regularExpression) != nil
    }
    static func read(_ url: URL) throws -> PageReference {
        let granted = url.startAccessingSecurityScopedResource()
        defer { if granted { url.stopAccessingSecurityScopedResource() } }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size > 0, size < maximumBytes else { throw ReferenceError.invalid }
        let data = try Data(contentsOf: url)
        guard data.count < maximumBytes else { throw ReferenceError.invalid }
        let ref = try JSONDecoder().decode(PageReference.self, from: data)
        guard (ref.version == 1 || ref.version == 2), isValidID(ref.pageID), ref.title.count < 300,
              (ref.version == 1 && ref.html == nil) || (ref.version == 2 && !(ref.html?.isEmpty ?? true)) else { throw ReferenceError.invalid }
        return ref
    }
    /// Keep embedded React interactions, but prevent network requests, remote resources and forms.
    /// No remote base URL and no native JavaScript bridge are provided.
    static func isolatedHTML(_ raw: String) -> String {
        let policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
        let meta = "<meta http-equiv=\"Content-Security-Policy\" content=\"\(policy)\">"
        let noRefresh = raw.replacingOccurrences(of: "<meta\\b[^>]*http-equiv\\s*=\\s*[\"']?refresh[^>]*>", with: "", options: [.regularExpression, .caseInsensitive])
        if let range = noRefresh.range(of: "<head[^>]*>", options: [.regularExpression, .caseInsensitive]) {
            var result = noRefresh; result.insert(contentsOf: meta, at: range.upperBound); return result
        }
        return "<!doctype html><html><head>\(meta)<meta name='viewport' content='width=device-width,initial-scale=1'></head><body>\(noRefresh)</body></html>"
    }
    enum ReferenceError: LocalizedError {
        case invalid
        var errorDescription: String? { "This isn’t a valid Hermes Page document." }
    }
}
