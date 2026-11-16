import SwiftUI

@main struct HermesPagesApp: App {
    @StateObject private var store = PageStore()
    @State private var document: PageReference?
    var body: some Scene {
        WindowGroup {
            LibraryView(store: store)
                .sheet(item: $document) { doc in SnapshotReader(document: doc) }
                .onOpenURL { url in
                    Task {
                        if url.isFileURL, let ref = try? PageReference.read(url) {
                            if ref.html != nil { document = ref }
                            else {
                                await store.refresh()
                                store.selected = store.pages.first { $0.id == ref.pageID }
                            }
                        } else { await store.openCard(url) }
                    }
                }
        }
    }
}

struct SnapshotReader: View {
    let document: PageReference
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            PageWebView(html: PageReference.isolatedHTML(document.html ?? ""), base: nil, openExternal: { _ in })
                .navigationTitle(document.title).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
