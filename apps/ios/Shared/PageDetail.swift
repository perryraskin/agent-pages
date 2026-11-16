import SwiftUI
import WebKit
import SafariServices

struct PageRevealStyle {
    let reduceMotion: Bool
    var duration: Double { reduceMotion ? 0.12 : 0.32 }
    var initialOffset: CGFloat { reduceMotion ? 0 : 6 }
    var animation: Animation { .easeOut(duration: duration) }
}

/// Static article-shaped placeholders, not another animated progress indicator.
/// The reader crossfades over this surface only after WebKit has visible content.
struct PageLoadingPlaceholder: View {
    var body: some View {
        VStack(spacing: 30) {
            VStack(spacing: 13) {
                Capsule().fill(Color.pageInk.opacity(0.07)).frame(width: 112, height: 34)
                Capsule().fill(Color.secondaryInk.opacity(0.07)).frame(width: 82, height: 13)
            }.frame(maxWidth: .infinity).padding(.top, 34).padding(.bottom, 12)
            VStack(alignment: .leading, spacing: 24) {
                RoundedRectangle(cornerRadius: 8).fill(Color.pageInk.opacity(0.06))
                    .frame(maxWidth: 230).frame(height: 30)
                VStack(alignment: .leading, spacing: 11) {
                    line(); line().padding(.trailing, 32)
                }
                VStack(spacing: 0) {
                    ForEach(0..<3) { row in
                        VStack(alignment: .leading, spacing: 11) {
                            line().frame(maxWidth: 80)
                            line().frame(maxWidth: row == 1 ? 170 : 120)
                        }.padding(19).frame(maxWidth: .infinity, alignment: .leading)
                        if row < 2 { Color.secondaryInk.opacity(0.045).frame(height: 1) }
                    }
                }.background(Color.hermes.opacity(0.025), in: RoundedRectangle(cornerRadius: 16))
            }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.pageSurface, in: RoundedRectangle(cornerRadius: 25))
            Spacer(minLength: 0)
        }.padding(.horizontal, 20).padding(.bottom, 20)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Color.paper)
            .allowsHitTesting(false)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Loading Page")
            .accessibilityIdentifier("page-loading-placeholder")
    }
    private func line() -> some View {
        Capsule().fill(Color.secondaryInk.opacity(0.07)).frame(height: 10)
    }
}

struct PageDetail: View {
    @ObservedObject var store: PageStore
    let page: Page
    var insertPage: ((Page) -> Void)?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var html: String?
    @State private var error: String?
    @State private var sharing = false
    @State private var confirmCard = false
    @State private var externalLink: ReaderLink?
    @State private var rendered = false
    @State private var reloadID = UUID()
    var body: some View {
        ZStack {
            if let error {
                VStack(spacing: 18) {
                    ContentUnavailableView("Couldn’t open this Page", systemImage: "wifi.exclamationmark", description: Text(error))
                    Button("Try again") { html = nil; self.error = nil; rendered = false; reloadID = UUID() }
                        .buttonStyle(.borderedProminent).padding(.bottom, 32)
                }
            } else {
                if let html {
                    PageWebView(html: html, base: try? store.contentURL(page),
                                openExternal: { externalLink = ReaderLink(url: $0) },
                                onReady: revealPage,
                                onFailure: { self.error = $0 })
                        .id(reloadID)
                        .opacity(rendered ? 1 : 0)
                        .offset(y: rendered ? 0 : PageRevealStyle(reduceMotion: reduceMotion).initialOffset)
                        .allowsHitTesting(rendered)
                        .accessibilityHidden(!rendered)
                }
                if !rendered { PageLoadingPlaceholder().transition(.opacity) }
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.paper).navigationTitle(page.title).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { store.toggleFavorite(page) } label: { Image(systemName: store.favorites.contains(page.id) ? "star.fill" : "star") }.accessibilityLabel("Favorite Page")
                    Button { sharing = true } label: { Image(systemName: "square.and.arrow.up") }.accessibilityLabel("Share Page")
                }
                if insertPage != nil {
                    ToolbarItem(placement: .bottomBar) {
                        Button { confirmCard = true } label: { Label("Insert private Page card", systemImage: "message.fill").font(.headline) }
                    }
                }
            }
            .confirmationDialog("Insert a private Page card?", isPresented: $confirmCard, titleVisibility: .visible) {
                Button("Insert card") { insertPage?(page) }
            } message: { Text("This sends the Page title and a private link. Only devices with Hermes Pages and access to your tailnet can read it. Messages will let you review before sending.") }
            .sheet(isPresented: $sharing) { SharePageView(store: store, page: page) }
            .sheet(item: $externalLink) { link in ReaderBrowser(url: link.url) }
            .task(id: reloadID) {
                do {
                    let data = try await store.request("v1/pages/\(page.id)/content")
                    guard let text = String(data: data, encoding: .utf8) else { throw URLError(.cannotDecodeContentData) }
                    guard !Task.isCancelled else { return }
                    html = text
                } catch is CancellationError { }
                catch { if !Task.isCancelled { self.error = error.localizedDescription } }
            }
    }
    private func revealPage() {
        guard !rendered else { return }
        withAnimation(PageRevealStyle(reduceMotion: reduceMotion).animation) { rendered = true }
    }
}

struct PageWebView: UIViewRepresentable {
    let html: String
    let base: URL?
    let openExternal: (URL) -> Void
    var onReady: () -> Void = {}
    var onFailure: (String) -> Void = { _ in }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.backgroundColor = .clear
        context.coordinator.load(html: html, base: base, into: view)
        return view
    }
    func updateUIView(_ view: WKWebView, context: Context) {
        context.coordinator.load(html: html, base: base, into: view)
    }
    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        coordinator.timeout?.cancel()
        view.stopLoading()
        view.navigationDelegate = nil
    }
    func makeCoordinator() -> Coordinator { Coordinator(openExternal: openExternal, onReady: onReady, onFailure: onFailure) }
    final class Coordinator: NSObject, WKNavigationDelegate {
        let openExternal: (URL) -> Void
        let onReady: () -> Void
        let onFailure: (String) -> Void
        var timeout: DispatchWorkItem?
        private var loadedHTML: String?
        private var loadedBase: URL?
        private var recoveredProcess = false
        private var renderGeneration = UUID()
        init(openExternal: @escaping (URL) -> Void, onReady: @escaping () -> Void, onFailure: @escaping (String) -> Void) {
            self.openExternal = openExternal; self.onReady = onReady; self.onFailure = onFailure
        }
        func load(html: String, base: URL?, into view: WKWebView, force: Bool = false) {
            guard force || loadedHTML != html || loadedBase != base else { return }
            loadedHTML = html; loadedBase = base
            renderGeneration = UUID()
            timeout?.cancel()
            let deadline = DispatchWorkItem { [weak self] in
                self?.onFailure("The Page reader did not finish loading. Check your connection and try again.")
            }
            timeout = deadline
            DispatchQueue.main.asyncAfter(deadline: .now() + 20, execute: deadline)
            view.loadHTMLString(html, baseURL: base)
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            checkVisibleContent(webView, generation: renderGeneration, attempt: 0)
        }
        private func checkVisibleContent(_ webView: WKWebView, generation: UUID, attempt: Int) {
            webView.evaluateJavaScript("Boolean((document.getElementById('root') || document.body)?.innerText.trim().length)") { [weak self, weak webView] result, error in
                guard let self, let webView, self.renderGeneration == generation else { return }
                if error == nil, result as? Bool == true {
                    self.timeout?.cancel(); self.onReady()
                } else if error == nil, attempt < 50 {
                    // A document can finish navigating before its asynchronous
                    // React render commits. Give it a bounded render window.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self, weak webView] in
                        guard let self, let webView, self.renderGeneration == generation else { return }
                        self.checkVisibleContent(webView, generation: generation, attempt: attempt + 1)
                    }
                } else {
                    self.timeout?.cancel(); self.onFailure("This Page loaded without visible content. Try again.")
                }
            }
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { fail(error) }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { fail(error) }
        private func fail(_ error: Error) {
            guard (error as NSError).code != NSURLErrorCancelled else { return }
            timeout?.cancel(); onFailure(error.localizedDescription)
        }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            guard !recoveredProcess, let html = loadedHTML else {
                timeout?.cancel(); onFailure("The Page reader stopped. Try again to reopen this Page."); return
            }
            recoveredProcess = true
            load(html: html, base: loadedBase, into: webView, force: true)
        }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void) {
            guard action.navigationType == .linkActivated else { decisionHandler(.allow); return }
            // Preserve in-document navigation; don't let a Page replace the native reader with arbitrary sites.
            if let url = action.request.url, url.fragment != nil,
               url.host == webView.url?.host, url.path == webView.url?.path { decisionHandler(.allow) }
            else {
                decisionHandler(.cancel)
                if let url = action.request.url, ["https", "http"].contains(url.scheme ?? "") { openExternal(url) }
            }
        }
    }
}

struct ReaderLink: Identifiable { let url: URL; var id: String { url.absoluteString } }
struct ReaderBrowser: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

struct SharePageView: View {
    @ObservedObject var store: PageStore
    let page: Page
    @Environment(\.dismiss) var dismiss
    @State private var days = 7
    @State private var confirmed = false
    @State private var busy = false
    @State private var url: URL?
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Label("Share a snapshot", systemImage: "doc.badge.arrow.up").font(.title3.weight(.semibold))
                    Text(page.title).font(.headline)
                    Text("This makes the entire current Page readable to anyone holding its link, including any financial or personal information it contains. Later edits stay private.").font(.subheadline).foregroundStyle(.secondary)
                }
                if let url {
                    Section("Your link is ready") {
                        ShareLink(item: url) { Label("Share link…", systemImage: "square.and.arrow.up") }
                        Text("Expires in \(days) day\(days == 1 ? "" : "s"). Revoke it anytime in Settings → Shared snapshots. Downloads cannot be recalled.").font(.footnote).foregroundStyle(.secondary)
                    }
                } else {
                    Section {
                        Picker("Link expires", selection: $days) { Text("1 day").tag(1); Text("7 days").tag(7); Text("30 days").tag(30) }
                        Toggle("I’ve reviewed this Page for private information", isOn: $confirmed)
                        Button {
                            busy = true; error = nil
                            Task {
                                defer { busy = false }
                                do { url = try await store.createShare(page, days: days).url }
                                catch { self.error = error.localizedDescription }
                            }
                        } label: { if busy { ProgressView() } else { Text("Create share link") } }.disabled(!confirmed || busy)
                    } footer: { Text("Preview cards use a generic label, not a screenshot of this Page. Snapshots are read-only; interactive controls are disabled. Prototype links also stop working if the sharing tunnel restarts.") }
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }.navigationTitle("Share Page").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
