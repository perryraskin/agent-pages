// Narrow, owner-scoped Messages-side helper. No edits to BlueBubbles or Hermes.
// Private selectors follow the shipped IMCore shape; every optional selector is checked.
#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <sys/stat.h>
#import <unistd.h>

static NSString *ipc;
static NSSet *targets;
static NSTimer *timer;
static id obj(id target, NSString *name) {
    SEL sel = NSSelectorFromString(name);
    return [target respondsToSelector:sel] ? ((id(*)(id,SEL))objc_msgSend)(target,sel) : nil;
}
static id arg(id target, NSString *name, id value) {
    SEL sel = NSSelectorFromString(name);
    return [target respondsToSelector:sel] ? ((id(*)(id,SEL,id))objc_msgSend)(target,sel,value) : nil;
}
static NSDictionary *handle(NSDictionary *request) {
    if ([request[@"action"] isEqual:@"probe"]) {
        Class composition = NSClassFromString(@"CKComposition");
        Class conversation = NSClassFromString(@"CKConversation");
        BOOL ready = composition && conversation && NSClassFromString(@"IMChatRegistry") &&
            [composition instancesRespondToSelector:NSSelectorFromString(@"initWithText:subject:shelfPluginPayload:shelfMediaObject:")] &&
            [composition instancesRespondToSelector:NSSelectorFromString(@"messagesFromCompositionFirstGUIDForMessage:sendingService:")] &&
            [conversation instancesRespondToSelector:NSSelectorFromString(@"sendMessage:onService:newComposition:")] &&
            [NSClassFromString(@"IMFileTransferCenter") instancesRespondToSelector:NSSelectorFromString(@"guidForNewOutgoingTransferWithLocalURL:")] &&
            [NSClassFromString(@"IMFileTransferCenter") instancesRespondToSelector:NSSelectorFromString(@"registerTransferWithDaemon:")] &&
            [NSClassFromString(@"IMMessage") instancesRespondToSelector:NSSelectorFromString(@"_updateFileTransferGUIDs:")];
        return @{@"ok":@YES,@"protocol":@2,@"pid":@(getpid()),@"balloon":@(ready),@"previewArtwork":@YES};
    }
    NSString *target = request[@"target"];
    if (![targets containsObject:target] || ![request[@"action"] isEqual:@"send"])
        return @{@"ok":@NO,@"error":@"Target/action not allowed"};
    NSString *bundle = [[NSProcessInfo processInfo] environment][@"AGENT_PAGES_BALLOON_BUNDLE"];
    if (!bundle.length) return @{@"ok":@NO,@"error":@"Configure AGENT_PAGES_BALLOON_BUNDLE"};
    NSData *payload = [[NSData alloc] initWithBase64EncodedString:request[@"payload"] options:0];
    if (!payload.length || payload.length > 1000000)
        return @{@"ok":@NO,@"error":@"Invalid Page archive"};
    NSString *guid = request[@"id"];
    NSString *expectedPath = [[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Messages/Attachments/HermesPages"] stringByAppendingPathComponent:[guid stringByAppendingString:@".jpeg"]];
    NSString *previewPath = request[@"previewPath"];
    struct stat previewStat;
    if (![previewPath isEqualToString:expectedPath] ||
        ![[previewPath stringByResolvingSymlinksInPath] isEqualToString:expectedPath] ||
        lstat(previewPath.fileSystemRepresentation,&previewStat) || !S_ISREG(previewStat.st_mode) ||
        previewStat.st_uid != getuid() || previewStat.st_size < 1000 || previewStat.st_size > 1000000)
        return @{@"ok":@NO,@"error":@"Native Page artwork is required"};
    id registry = obj(NSClassFromString(@"IMChatRegistry"), @"sharedInstance");
    id chat = arg(registry,@"existingChatWithGUID:",[@"iMessage;-;" stringByAppendingString:target]);
    if (!chat) return @{@"ok":@NO,@"error":@"Exact iMessage DM not found"};
    id list = obj(NSClassFromString(@"CKConversationList"), @"sharedConversationList");
    id conversation = arg(list,@"conversationForExistingChat:",chat);
    if (!conversation) conversation = arg(list,@"conversationForChat:",chat);
    id service = obj(conversation,@"sendingService");
    Class cls = NSClassFromString(@"CKComposition");
    SEL init = NSSelectorFromString(@"initWithText:subject:shelfPluginPayload:shelfMediaObject:");
    SEL messages = NSSelectorFromString(@"messagesFromCompositionFirstGUIDForMessage:sendingService:");
    SEL send = NSSelectorFromString(@"sendMessage:onService:newComposition:");
    if (!service || ![cls instancesRespondToSelector:init] || ![conversation respondsToSelector:send])
        return @{@"ok":@NO,@"error":@"Composition selectors unavailable on this macOS"};
    id transferCenter = obj(NSClassFromString(@"IMFileTransferCenter"),@"sharedInstance");
    SEL registerTransfer = NSSelectorFromString(@"registerTransferWithDaemon:");
    if (![transferCenter respondsToSelector:registerTransfer])
        return @{@"ok":@NO,@"error":@"Native preview transfer API unavailable"};
    NSString *transfer = arg(transferCenter,@"guidForNewOutgoingTransferWithLocalURL:",[NSURL fileURLWithPath:previewPath]);
    if (![transfer isKindOfClass:NSString.class] || !transfer.length)
        return @{@"ok":@NO,@"error":@"Could not stage native Page artwork"};
    ((void(*)(id,SEL,id))objc_msgSend)(transferCenter,registerTransfer,transfer);
    NSAttributedString *text = [[NSAttributedString alloc] initWithString:@"\uFFFC"
        attributes:@{@"__kIMMessagePartAttributeName":@0,
                     @"__kIMFileTransferGUIDAttributeName":transfer,
                     @"__kIMFilenameAttributeName":previewPath.lastPathComponent}];
    id composition = ((id(*)(id,SEL,id,id,id,id))objc_msgSend)([cls alloc],init,text,nil,nil,nil);
    if (![composition respondsToSelector:messages])
        return @{@"ok":@NO,@"error":@"Composition API unavailable"};
    NSArray *items = ((id(*)(id,SEL,id,id))objc_msgSend)(composition,messages,guid,service);
    if (![items isKindOfClass:[NSArray class]] || items.count != 1)
        return @{@"ok":@NO,@"error":@"Expected one Page message"};
    id message = items[0];
    SEL setTransfers = NSSelectorFromString(@"_updateFileTransferGUIDs:");
    if (![message respondsToSelector:setTransfers])
        return @{@"ok":@NO,@"error":@"Preview transfer setter unavailable"};
    ((void(*)(id,SEL,id))objc_msgSend)(message,setTransfers,@[transfer]);
    if (![obj(message,@"fileTransferGUIDs") containsObject:transfer])
        return @{@"ok":@NO,@"error":@"Artwork was not attached; refusing caption-only send"};
    SEL setBalloon = NSSelectorFromString(@"setBalloonBundleID:");
    SEL setPayload = NSSelectorFromString(@"setPayloadData:");
    if (![message respondsToSelector:setBalloon] || ![message respondsToSelector:setPayload])
        return @{@"ok":@NO,@"error":@"Balloon setters unavailable"};
    ((void(*)(id,SEL,id))objc_msgSend)(message,setBalloon,bundle);
    ((void(*)(id,SEL,id))objc_msgSend)(message,setPayload,payload);
    if (![obj(message,@"balloonBundleID") isEqual:bundle] ||
        ![obj(message,@"payloadData") isEqual:payload])
        return @{@"ok":@NO,@"error":@"Payload verification failed before send"};
    ((void(*)(id,SEL,id,id,BOOL))objc_msgSend)(conversation,send,message,service,YES);
    return @{@"ok":@YES,@"guid":obj(message,@"guid") ?: guid,@"balloon":@YES,
             @"payloadBytes":@(payload.length),@"previewTransferGUID":transfer};
}

static void tick(void) {
    @autoreleasepool {
        NSArray *names = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:ipc error:nil];
        for (NSString *name in names) {
            if (![name hasSuffix:@".request.json"]) continue;
            NSString *identity = [name stringByReplacingOccurrencesOfString:@".request.json" withString:@""];
            if (![[NSUUID alloc] initWithUUIDString:identity]) continue;
            NSString *path = [ipc stringByAppendingPathComponent:name];
            NSString *claim = [ipc stringByAppendingPathComponent:[identity stringByAppendingString:@".claimed"]];
            // Atomic rename claims once; abandoned claims are never replayed after a crash.
            if (rename(path.fileSystemRepresentation,claim.fileSystemRepresentation) != 0) continue;
            NSDictionary *response;
            @try {
                struct stat st;
                if (lstat(claim.fileSystemRepresentation,&st) || !S_ISREG(st.st_mode) || st.st_uid != getuid() || st.st_size > 1500000)
                    response = @{@"ok":@NO,@"error":@"Invalid request file"};
                else {
                    NSDictionary *request = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:claim] options:0 error:nil];
                    response = [request[@"id"] isEqual:identity] ? handle(request) : @{@"ok":@NO,@"error":@"ID mismatch"};
                }
            } @catch (NSException *exception) {
                response = @{@"ok":@NO,@"error":@"Messages rejected this private API operation"};
            }
            NSData *data = [NSJSONSerialization dataWithJSONObject:response options:0 error:nil];
            NSString *out = [ipc stringByAppendingPathComponent:[identity stringByAppendingString:@".response.json"]];
            [data writeToFile:out atomically:YES]; chmod(out.fileSystemRepresentation,0600);
        }
    }
}

__attribute__((constructor)) static void start(void) {
    @autoreleasepool {
        if (![[NSProcessInfo processInfo].processName isEqual:@"Messages"]) return;
        NSDictionary *env = [NSProcessInfo processInfo].environment;
        ipc = [env[@"HERMES_PAGE_IPC"] copy];
        targets = [NSSet setWithArray:[env[@"HERMES_PAGE_TARGETS"] componentsSeparatedByString:@","] ?: @[]];
        struct stat st;
        if (!ipc || lstat(ipc.fileSystemRepresentation,&st) || !S_ISDIR(st.st_mode) || st.st_uid != getuid() || (st.st_mode & 0077)) return;
        dispatch_async(dispatch_get_main_queue(), ^{
            timer = [NSTimer scheduledTimerWithTimeInterval:0.25 repeats:YES block:^(NSTimer *t){ tick(); }];
        });
    }
}
