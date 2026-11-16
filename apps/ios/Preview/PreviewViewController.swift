import UIKit
import WebKit
import QuickLook

/// Hosted by the system's Quick Look drawer, not by the standalone app or Messages picker.
final class PreviewViewController: UIViewController, @preconcurrency QLPreviewingController, WKNavigationDelegate {
    private var web: WKWebView?
    private var task: Task<Void, Never>?
    private var previewCompletion: ((Error?) -> Void)?
    override func loadView() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: config)
        view.isOpaque = false
        view.backgroundColor = .systemBackground
        view.scrollView.contentInsetAdjustmentBehavior = .never
        view.navigationDelegate = self
        self.web = view
        let container = UIView()
        container.backgroundColor = .systemBackground
        view.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(view)
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: container.safeAreaLayoutGuide.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: container.safeAreaLayoutGuide.trailingAnchor),
            view.topAnchor.constraint(equalTo: container.safeAreaLayoutGuide.topAnchor),
            view.bottomAnchor.constraint(equalTo: container.safeAreaLayoutGuide.bottomAnchor)
        ])
        self.view = container
        // Quick Look's floating overlay chrome does not inset a hosted extension's web content.
        // Reserve a content-safe band so the first heading is not under its glass/gradient.
        additionalSafeAreaInsets = UIEdgeInsets(top: 88, left: 0, bottom: 52, right: 0)
    }
    func preparePreviewOfFile(at url: URL, completionHandler handler: @escaping (Error?) -> Void) {
        loadViewIfNeeded()
        previewCompletion = handler
        task = Task { @MainActor in
            var stage = "reference"
            do {
                let ref = try PageReference.read(url)
                if let html = ref.html {
                    self.title = ref.title
                    self.web?.loadHTMLString(PageReference.isolatedHTML(html), baseURL: nil)
                    return
                }
                stage = "network"
                let store = PageStore()
                let data = try await store.request("v1/pages/\(ref.pageID)/content")
                guard let text = String(data: data, encoding: .utf8) else { throw URLError(.cannotDecodeContentData) }
                stage = "render"
                let page = Page(id: ref.pageID, title: ref.title, updatedAt: "", automatic: false)
                self.title = ref.title
                self.web?.loadHTMLString(text, baseURL: try store.contentURL(page))
            } catch {
                // Finish the extension request even on network failure; show useful native preview instead of a generic file.
                let ns = error as NSError
                let message = "Couldn’t open this private Page. Connect to Tailscale and make sure your Mac is online. Diagnostic: \(stage) \(ns.domain) \(ns.code)."
                self.web?.loadHTMLString("<html><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{font:17px -apple-system;padding:24px;color-scheme:light dark}h1{font-size:25px}</style><h1>Hermes Pages</h1><p>\(message)</p></html>", baseURL: nil)
            }
        }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        webView.scrollView.setContentOffset(.zero, animated: false)
        let completion = previewCompletion; previewCompletion = nil
        completion?(nil)
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let completion = previewCompletion; previewCompletion = nil; completion?(error)
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let completion = previewCompletion; previewCompletion = nil; completion?(error)
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void) {
        // Embedded documents must not navigate to a network origin, even from script.
        let scheme = action.request.url?.scheme?.lowercased() ?? "about"
        decisionHandler(["http", "https", "javascript"].contains(scheme) ? .cancel : .allow)
    }
    deinit { task?.cancel() }
}
