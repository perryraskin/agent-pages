import Messages
import SwiftUI
import UIKit

final class MessagesViewController: MSMessagesAppViewController {
    private let store = PageStore()
    private let entry = MessageEntry()
    private var host: UIHostingController<MessageEntryView>?
    private var openedCardURL: URL?
    override func viewDidLoad() {
        super.viewDidLoad()
        let root = MessageEntryView(store: store, entry: entry,
            insertPage: { [weak self] page in self?.insert(page) },
            expand: { [weak self] in self?.requestPresentationStyle(.expanded) })
        let controller = UIHostingController(rootView: root)
        addChild(controller)
        controller.view.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(controller.view)
        NSLayoutConstraint.activate([
            controller.view.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            controller.view.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            controller.view.topAnchor.constraint(equalTo: view.topAnchor),
            controller.view.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
        controller.didMove(toParent: self)
        host = controller
    }
    override func willBecomeActive(with conversation: MSConversation) {
        super.willBecomeActive(with: conversation)
        entry.prepare()
        openedCardURL = nil
        // Resolve the received card BEFORE installing/showing the SwiftUI root.
        // Manual picker entry stays neutral until activation confirms no card.
        _ = stageCard(conversation.selectedMessage)
        loadViewIfNeeded()
    }
    override func didBecomeActive(with conversation: MSConversation) {
        super.didBecomeActive(with: conversation)
        finishActivation(conversation)
    }
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        if let conversation = activeConversation { finishActivation(conversation) }
    }
    override func didResignActive(with conversation: MSConversation) {
        super.didResignActive(with: conversation)
        openedCardURL = nil
    }
    override func didSelect(_ message: MSMessage, conversation: MSConversation) {
        guard stageCard(message) else { return }
        loadViewIfNeeded()
        if view.window != nil { requestPresentationStyle(.expanded) }
    }
    @discardableResult private func stageCard(_ message: MSMessage?) -> Bool {
        guard let message, let url = message.url else { return false }
        if openedCardURL == url, case .page = entry.route { return true }
        openedCardURL = url
        let title = (message.layout as? MSMessageTemplateLayout)?.caption
        entry.showCard(url, title: title, store: store)
        return true
    }
    private func finishActivation(_ conversation: MSConversation) {
        if entry.route == .waiting {
            if !stageCard(conversation.selectedMessage) {
                store.selected = nil
                entry.showLibrary()
            }
        }
        if presentationStyle != .expanded { requestPresentationStyle(.expanded) }
    }
    private func insert(_ page: Page) {
        guard let conversation = activeConversation else { return }
        do {
            let message = MSMessage(session: MSSession())
            message.url = try store.cardURL(page)
            message.summaryText = "Hermes Page: \(page.title)"
            let layout = MSMessageTemplateLayout()
            layout.caption = page.title
            layout.subcaption = "Private · Hermes Pages"
            layout.trailingSubcaption = "Tap to open"
            layout.image = cardImage(title: page.title)
            message.layout = layout
            conversation.insert(message) { [weak self] error in
                Task { @MainActor in
                    if let error { self?.store.error = "Couldn’t insert card: \(error.localizedDescription)" }
                    else { self?.requestPresentationStyle(.compact) }
                }
            }
        } catch { store.error = error.localizedDescription }
    }
    private func cardImage(title: String) -> UIImage {
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 600, height: 300))
        return renderer.image { c in
            UIColor(red: 0.957, green: 0.945, blue: 0.933, alpha: 1).setFill()
            c.fill(CGRect(x: 0, y: 0, width: 600, height: 300))
            let ink = UIColor(red: 0.286, green: 0.220, blue: 0.196, alpha: 1)
            let sage = UIColor(red: 0.322, green: 0.475, blue: 0.424, alpha: 1)
            let display = UIFont(name: "InstrumentSerif-Regular", size: 38) ?? .systemFont(ofSize: 38, weight: .regular)
            ("Hermes" as NSString).draw(at: CGPoint(x: 96, y: 20), withAttributes: [.font: display, .foregroundColor: ink])
            ("PAGE" as NSString).draw(at: CGPoint(x: 515, y: 39), withAttributes: [.font: UIFont.systemFont(ofSize: 11, weight: .medium), .foregroundColor: sage])
            UIColor(red: 0.992, green: 0.988, blue: 0.984, alpha: 1).setFill()
            UIBezierPath(roundedRect: CGRect(x: 22, y: 88, width: 556, height: 192), cornerRadius: 22).fill()
            let style = NSMutableParagraphStyle(); style.lineBreakMode = .byTruncatingTail
            let titleFont = UIFont(name: "InstrumentSerif-Regular", size: 42) ?? .systemFont(ofSize: 40, weight: .regular)
            (title as NSString).draw(in: CGRect(x: 44, y: 113, width: 510, height: 106), withAttributes: [.font: titleFont, .foregroundColor: ink, .paragraphStyle: style])
            ("Made for you" as NSString).draw(at: CGPoint(x: 44, y: 247), withAttributes: [.font: UIFont.systemFont(ofSize: 12, weight: .regular), .foregroundColor: sage])
        }
    }
}
