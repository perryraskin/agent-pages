import Foundation
import SwiftUI

struct Page: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let updatedAt: String
    let automatic: Bool
    let tags: [String]
    init(id: String, title: String, updatedAt: String, automatic: Bool, tags: [String] = []) {
        self.id = id; self.title = title; self.updatedAt = updatedAt; self.automatic = automatic
        self.tags = Array(Set(tags)).sorted()
    }
    private enum CodingKeys: String, CodingKey { case id, title, updatedAt, automatic, tags }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.init(id: try c.decode(String.self, forKey: .id), title: try c.decode(String.self, forKey: .title),
                  updatedAt: try c.decode(String.self, forKey: .updatedAt), automatic: try c.decode(Bool.self, forKey: .automatic),
                  tags: try c.decodeIfPresent([String].self, forKey: .tags) ?? [])
    }
    func matches(query: String, tag: String? = nil) -> Bool {
        guard tag == nil || tags.contains(tag!) else { return false }
        let normalize: (String) -> String = {
            $0.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
                .replacingOccurrences(of: "-", with: " ")
        }
        let words = normalize(query).split(whereSeparator: { $0.isWhitespace })
        let haystack = normalize(([title, id] + tags).joined(separator: " "))
        return words.allSatisfy { haystack.contains($0) }
    }
    var date: Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: updatedAt) ?? ISO8601DateFormatter().date(from: updatedAt)
    }
    static func validID(_ s: String) -> Bool {
        PageReference.isValidID(s)
    }
}
struct PageResponse: Decodable { let pages: [Page] }
struct SharedPage: Decodable, Identifiable {
    let id: String
    let slug: String
    let title: String
    let created: Double
    let expires: Double
    let revoked: Int
    var active: Bool { revoked == 0 && Date(timeIntervalSince1970: expires) > Date() }
}
struct ShareResponse: Decodable { let shares: [SharedPage] }
struct CreatedShare: Decodable { let id: String; let url: URL }
struct ServiceError: Decodable { let error: String }

@MainActor final class PageStore: ObservableObject {
    static let group = "group.org.example.agentpages"
    static let defaultServer = "https://pages.example.invalid"
    private let defaults = UserDefaults(suiteName: group) ?? .standard
    @Published var pages: [Page] = []
    @Published var loading = false
    @Published var error: String?
    @Published var selected: Page?
    @Published var server: String { didSet { defaults.set(server, forKey: "server") } }
    @Published var favorites: Set<String> { didSet { defaults.set(Array(favorites), forKey: "favorites") } }
    @Published var shares: [SharedPage] = []
    @Published private(set) var readerGeneration = UUID()
    private var refreshTask: Task<Void, Never>?
    private var pendingCardURL: URL?
    private var openRequestID: UUID?
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
        server = defaults.string(forKey: "server") ?? Self.defaultServer
        favorites = Set(defaults.stringArray(forKey: "favorites") ?? [])
    }
    func endpoint(_ path: String) throws -> URL {
        guard let base = URL(string: server), base.scheme == "https", base.host != nil,
              base.user == nil, base.password == nil, base.query == nil, base.fragment == nil,
              base.path.isEmpty || base.path == "/" else { throw URLError(.badURL) }
        return base.appendingPathComponent(path)
    }
    func contentURL(_ page: Page) throws -> URL {
        guard Page.validID(page.id) else { throw URLError(.badURL) }
        return try endpoint("v1/pages/\(page.id)/content")
    }
    func cardURL(_ page: Page) throws -> URL {
        var c = URLComponents(url: try contentURL(page), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "hermesPage", value: page.id)]
        return c.url!
    }
    func pageID(from url: URL) -> String? {
        guard let expected = try? endpoint(""), url.scheme == "https", url.host == expected.host, url.port == expected.port,
              let id = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "hermesPage" })?.value,
              Page.validID(id), url.path == "/v1/pages/\(id)/content" else { return nil }
        return id
    }
    func request(_ path: String, body: [String: Any]? = nil) async throws -> Data {
        var request = URLRequest(url: try endpoint(path), timeoutInterval: 20)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        if let body {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("ios", forHTTPHeaderField: "X-Hermes-Client")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
            let message = (try? JSONDecoder().decode(ServiceError.self, from: data).error) ?? "Server returned \(http.statusCode)."
            throw NSError(domain: "HermesPages", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: message])
        }
        return data
    }
    func refresh() async {
        // LibraryView.task and selected-message activation can arrive together.
        // Both callers must await the SAME load, not treat an in-flight load as
        // an empty library and incorrectly report that the selected Page vanished.
        if let refreshTask { await refreshTask.value; return }
        loading = true; error = nil
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.loading = false; self.refreshTask = nil }
            do { self.pages = try JSONDecoder().decode(PageResponse.self, from: await self.request("v1/pages")).pages }
            catch { self.error = "Couldn’t reach your private library. Check Tailscale and your Mac’s connection.\n\(error.localizedDescription)" }
        }
        refreshTask = task
        await task.value
    }
    func openCard(_ url: URL) async {
        let id: String
        if url.scheme == "hermespages", url.host == "page", Page.validID(String(url.path.dropFirst())) {
            id = String(url.path.dropFirst())
        } else if let cardID = pageID(from: url) { id = cardID }
        else { error = "This card does not contain a valid private Hermes Page link."; return }
        let requestID = UUID()
        openRequestID = requestID
        pendingCardURL = url
        error = nil
        // A Page created since the last library load must not be treated as
        // deleted just because an older cached list does not contain it.
        if !pages.contains(where: { $0.id == id }) { await refresh() }
        guard !Task.isCancelled, openRequestID == requestID else { return }
        // A network error is not evidence that a Page was deleted.
        guard error == nil else { return }
        selected = pages.first { $0.id == id }
        if selected == nil { error = "This Page is no longer in your library." }
        else { readerGeneration = UUID() }
    }
    func retry() async {
        if let pendingCardURL { await openCard(pendingCardURL) }
        else { await refresh() }
    }
    func toggleFavorite(_ page: Page) {
        if favorites.contains(page.id) { favorites.remove(page.id) } else { favorites.insert(page.id) }
    }
    func createShare(_ page: Page, days: Int) async throws -> CreatedShare {
        try JSONDecoder().decode(CreatedShare.self, from: await request("v1/shares", body: ["slug": page.id, "days": days]))
    }
    func loadShares() async throws {
        shares = try JSONDecoder().decode(ShareResponse.self, from: await request("v1/shares")).shares
    }
    func revoke(_ share: SharedPage) async throws {
        _ = try await request("v1/shares/\(share.id)/revoke", body: [:])
        try await loadShares()
    }
}

/// Extension entry is separate from LibraryView's navigation path: a received
/// card starts with its reader as the root, never a library followed by a push.
@MainActor final class MessageEntry: ObservableObject {
    enum Route: Equatable { case waiting, library, page(Page), invalid }
    @Published private(set) var route: Route = .waiting
    @Published private(set) var generation = UUID()

    func prepare() { route = .waiting }
    func showLibrary() { route = .library }
    func showCard(_ url: URL, title: String?, store: PageStore) {
        let id: String?
        if url.scheme == "hermespages", url.host == "page", Page.validID(String(url.path.dropFirst())) {
            id = String(url.path.dropFirst())
        } else { id = store.pageID(from: url) }
        guard let id else { route = .invalid; return }
        let cached = store.pages.first { $0.id == id }
        let caption = title?.trimmingCharacters(in: .whitespacesAndNewlines)
        let page = Page(id: id, title: caption?.isEmpty == false ? caption! : (cached?.title ?? "Hermes Page"),
                        updatedAt: cached?.updatedAt ?? "", automatic: cached?.automatic ?? false, tags: cached?.tags ?? [])
        // Stage synchronously, before the extension view becomes visible. The
        // reader fetches this Page's content directly; no library request needed.
        var transaction = Transaction(animation: nil)
        transaction.disablesAnimations = true
        withTransaction(transaction) {
            generation = UUID()
            route = .page(page)
        }
    }
}

extension Color {
    private static func editorial(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: 1)
        })
    }
    static let paper = editorial(light: 0xF4F1EE, dark: 0x1E1917)
    static let pageSurface = editorial(light: 0xFDFCFB, dark: 0x26211E)
    static let pageInk = editorial(light: 0x493832, dark: 0xF0E4DC)
    static let secondaryInk = editorial(light: 0x887A73, dark: 0xB5A69B)
    static let hermes = editorial(light: 0x52796C, dark: 0xA5C4B7)
}
