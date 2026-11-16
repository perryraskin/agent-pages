import XCTest
@testable import HermesPages

@MainActor final class AppTests: XCTestCase {
    func testTagsDecodeAndRoundTrip() throws {
        let raw = Data(#"{"id":"mjml-seo","title":"SEO plan","updatedAt":"","automatic":false,"tags":["seo","mjml","seo"]}"#.utf8)
        let page = try JSONDecoder().decode(Page.self, from: raw)
        XCTAssertEqual(page.tags, ["mjml", "seo"])
        XCTAssertEqual(try JSONDecoder().decode(Page.self, from: JSONEncoder().encode(page)), page)
    }
    func testOlderPagesWithoutTagsStillDecode() throws {
        let raw = Data(#"{"id":"demo","title":"Demo","updatedAt":"","automatic":false}"#.utf8)
        XCTAssertEqual(try JSONDecoder().decode(Page.self, from: raw).tags, [])
    }
    func testSearchFindsTagsAndRequiresEveryWord() {
        let page = Page(id: "seo-plan", title: "Growth plan", updatedAt: "", automatic: false,
                        tags: ["mjml", "seo", "project-pilot-pro"])
        XCTAssertTrue(page.matches(query: "MJML SEO"))
        XCTAssertTrue(page.matches(query: "project pilot", tag: "seo"))
        XCTAssertTrue(page.matches(query: "   "))
        XCTAssertFalse(page.matches(query: "mjml finance"))
        XCTAssertFalse(page.matches(query: "", tag: "finance"))
    }
    func testReceivedCardPreservesCachedTagsWithoutLoadingLibrary() throws {
        let store = fixtureStore()
        let page = Page(id: "fleet-health", title: "Fleet health", updatedAt: "", automatic: true, tags: ["fleet", "hermes"])
        store.pages = [page]
        let entry = MessageEntry()
        entry.showCard(try store.cardURL(page), title: page.title, store: store)
        guard case .page(let target) = entry.route else { return XCTFail("Expected reader") }
        XCTAssertEqual(target.tags, page.tags)
        XCTAssertEqual(PageTestProtocol.calls, 0)
    }
    func testPageRevealUsesAShortNonBouncyFade() {
        let style = PageRevealStyle(reduceMotion: false)
        XCTAssertEqual(style.duration, 0.32)
        XCTAssertEqual(style.initialOffset, 6)
    }
    func testReduceMotionRemovesMovementAndShortensFade() {
        let style = PageRevealStyle(reduceMotion: true)
        XCTAssertEqual(style.initialOffset, 0)
        XCTAssertLessThan(style.duration, PageRevealStyle(reduceMotion: false).duration)
        XCTAssertGreaterThan(style.duration, 0)
    }
    func testValidPageIDs() {
        XCTAssertTrue(Page.validID("recent-transactions"))
        for id in ["../private", "a/b", "", "<script>", "A", "a?x=1"] { XCTAssertFalse(Page.validID(id)) }
    }
    func testCardRoundTripAndUntrustedHosts() throws {
        let store = PageStore()
        let page = Page(id: "fleet-health", title: "Fleet health", updatedAt: "2026-11-11T12:00:00Z", automatic: true)
        let url = try store.cardURL(page)
        XCTAssertEqual(store.pageID(from: url), page.id)
        XCTAssertNil(store.pageID(from: URL(string: "https://evil.example/v1/pages/fleet-health/content?hermesPage=fleet-health")!))
        XCTAssertNil(store.pageID(from: URL(string: "https://pages.example.invalid/v1/pages/fleet-health/content?hermesPage=../../secret")!))
        XCTAssertNotNil(page.date)
    }
    func testInvalidOriginRejected() {
        let store = PageStore(); let original = store.server
        defer { store.server = original }
        for origin in ["http://example.com", "https://user:example-recipient", "https://example.com/private", "https://example.com?token=secret"] {
            store.server = origin
            XCTAssertThrowsError(try store.endpoint("v1/pages"))
        }
    }
    private func fixtureStore(status: Int = 200) -> PageStore {
        PageTestProtocol.status = status
        PageTestProtocol.calls = 0
        PageTestProtocol.data = Data("{\"pages\":[{\"id\":\"fleet-roster-auto\",\"title\":\"Fleet roster (auto)\",\"updatedAt\":\"2026-11-12T12:00:00Z\",\"automatic\":true}]}".utf8)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PageTestProtocol.self]
        return PageStore(session: URLSession(configuration: config))
    }
    func testCardEntryStagesReaderSynchronouslyWithoutLibraryRequest() throws {
        let store = fixtureStore()
        let entry = MessageEntry()
        XCTAssertEqual(entry.route, .waiting)
        let page = Page(id: "fleet-roster-auto", title: "Fleet roster (auto)", updatedAt: "", automatic: true)
        entry.showCard(try store.cardURL(page), title: page.title, store: store)
        guard case .page(let target) = entry.route else { return XCTFail("Card must be the root immediately") }
        XCTAssertEqual(target.id, page.id)
        XCTAssertEqual(target.title, page.title)
        XCTAssertEqual(PageTestProtocol.calls, 0)
        XCTAssertNil(store.selected, "Direct entry must not push onto LibraryView's path")
        XCTAssertTrue(store.pages.isEmpty, "No library load is needed to resolve a validated card")
    }
    func testLibraryOnlyAppearsWhenExplicitlyChosen() throws {
        let store = fixtureStore()
        let entry = MessageEntry()
        entry.prepare()
        XCTAssertEqual(entry.route, .waiting)
        entry.showLibrary()
        XCTAssertEqual(entry.route, .library)
        entry.showCard(try store.cardURL(Page(id: "fleet-health",title: "Fleet health",updatedAt: "",automatic: false)),
                       title: "Fleet health", store: store)
        guard case .page = entry.route else { return XCTFail("Card must replace, not push through, the library") }
        entry.showLibrary()
        XCTAssertEqual(entry.route, .library)
    }
    func testInvalidCardDoesNotFallBackToLibrary() {
        let store = fixtureStore()
        let entry = MessageEntry()
        entry.showCard(URL(string: "https://evil.example/page")!, title: "Untrusted", store: store)
        XCTAssertEqual(entry.route, .invalid)
        XCTAssertEqual(PageTestProtocol.calls, 0)
    }
    func testSwitchingCardsReplacesTheRootReader() throws {
        let store = fixtureStore()
        let entry = MessageEntry()
        for id in ["fleet-health", "fleet-roster-auto", "fleet-health"] {
            let prior = entry.generation
            entry.showCard(try store.cardURL(Page(id: id, title: id, updatedAt: "", automatic: false)),title: id,store: store)
            guard case .page(let target) = entry.route else { return XCTFail("Reader missing") }
            XCTAssertEqual(target.id,id)
            XCTAssertNotEqual(entry.generation,prior)
        }
        XCTAssertEqual(PageTestProtocol.calls,0)
    }
    func testConcurrentRefreshAndColdCardOpenAwaitOneLoad() async throws {
        let store = fixtureStore()
        let url = try store.cardURL(Page(id: "fleet-roster-auto", title: "Fleet", updatedAt: "", automatic: true))
        let refresh = Task { await store.refresh() }
        await Task.yield()
        await store.openCard(url)
        await refresh.value
        XCTAssertEqual(store.selected?.id, "fleet-roster-auto")
        XCTAssertNil(store.error)
        XCTAssertEqual(PageTestProtocol.calls, 1)
    }
    func testNewCardRefreshesAnOlderNonemptyLibrary() async throws {
        let store = fixtureStore()
        store.pages = [Page(id: "old-page", title: "Old", updatedAt: "", automatic: false)]
        let page = Page(id: "fleet-roster-auto", title: "Fleet", updatedAt: "", automatic: true)
        await store.openCard(try store.cardURL(page))
        XCTAssertEqual(store.selected?.id, page.id)
        XCTAssertNil(store.error)
        XCTAssertEqual(PageTestProtocol.calls, 1)
    }
    func testCardLoadFailureCanRetryTheSelectedCard() async throws {
        let store = fixtureStore(status: 503)
        let page = Page(id: "fleet-roster-auto", title: "Fleet", updatedAt: "", automatic: true)
        await store.openCard(try store.cardURL(page))
        XCTAssertNotNil(store.error)
        XCTAssertFalse(store.error?.contains("no longer") ?? true)
        PageTestProtocol.status = 200
        await store.retry()
        XCTAssertEqual(store.selected?.id, page.id)
        XCTAssertNil(store.error)
    }
    func testInvalidCardProducesVisibleError() async {
        let store = fixtureStore()
        await store.openCard(URL(string: "https://evil.example/page")!)
        XCTAssertNotNil(store.error)
        XCTAssertNil(store.selected)
        XCTAssertEqual(PageTestProtocol.calls, 0)
    }
    func testReopeningSameCardCreatesFreshReader() async throws {
        let store = fixtureStore()
        let page = Page(id: "fleet-roster-auto", title: "Fleet", updatedAt: "", automatic: true)
        store.pages = [page]
        let url = try store.cardURL(page)
        await store.openCard(url)
        let firstReader = store.readerGeneration
        await store.openCard(url)
        XCTAssertNotEqual(firstReader, store.readerGeneration)
        XCTAssertEqual(store.selected?.id, page.id)
    }
}

private final class PageTestProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var storedStatus = 200
    static var status: Int {
        get { lock.withLock { storedStatus } }
        set { lock.withLock { storedStatus = newValue } }
    }
    nonisolated(unsafe) private static var storedCalls = 0
    static var calls: Int {
        get { lock.withLock { storedCalls } }
        set { lock.withLock { storedCalls = newValue } }
    }
    nonisolated(unsafe) private static var storedData = Data()
    static var data: Data {
        get { lock.withLock { storedData } }
        set { lock.withLock { storedData = newValue } }
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.withLock { Self.storedCalls += 1 }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        let data = Self.data
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.05) { [self] in
            self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            self.client?.urlProtocol(self, didLoad: data)
            self.client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() { }
}
