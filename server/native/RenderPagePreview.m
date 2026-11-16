// Deterministic native artwork, rendered per Page title (not a stale template).
#import <AppKit/AppKit.h>
#import <CoreText/CoreText.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 4) return 2;
        NSString *title = [NSString stringWithUTF8String:argv[1]];
        NSString *destination = [NSString stringWithUTF8String:argv[2]];
        NSURL *font = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[3]]];
        CTFontManagerRegisterFontsForURL((__bridge CFURLRef)font,kCTFontManagerScopeProcess,NULL);
        NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(600,300)];
        [image lockFocusFlipped:YES];
        NSColor *paper = [NSColor colorWithSRGBRed:.957 green:.945 blue:.933 alpha:1];
        NSColor *ink = [NSColor colorWithSRGBRed:.286 green:.220 blue:.196 alpha:1];
        NSColor *sage = [NSColor colorWithSRGBRed:.322 green:.475 blue:.424 alpha:1];
        [paper setFill]; NSRectFill(NSMakeRect(0,0,600,300));
        NSFont *brand = [NSFont fontWithName:@"InstrumentSerif-Regular" size:38] ?: [NSFont systemFontOfSize:38];
        [@"Hermes" drawAtPoint:NSMakePoint(96,17) withAttributes:@{NSFontAttributeName:brand,NSForegroundColorAttributeName:ink}];
        [@"PAGE" drawAtPoint:NSMakePoint(526,39) withAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:11 weight:NSFontWeightMedium],NSForegroundColorAttributeName:sage}];
        [[NSColor colorWithSRGBRed:.992 green:.988 blue:.984 alpha:1] setFill];
        [[NSBezierPath bezierPathWithRoundedRect:NSMakeRect(22,88,556,192) xRadius:22 yRadius:22] fill];
        NSMutableParagraphStyle *style = [NSMutableParagraphStyle new];
        style.lineBreakMode = NSLineBreakByTruncatingTail;
        NSFont *display = [NSFont fontWithName:@"InstrumentSerif-Regular" size:42] ?: [NSFont systemFontOfSize:40];
        [title drawInRect:NSMakeRect(44,112,510,110) withAttributes:@{NSFontAttributeName:display,NSForegroundColorAttributeName:ink,NSParagraphStyleAttributeName:style}];
        [@"Made for you" drawAtPoint:NSMakePoint(44,248) withAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:12],NSForegroundColorAttributeName:sage}];
        [image unlockFocus];
        NSBitmapImageRep *bitmap = [NSBitmapImageRep imageRepWithData:image.TIFFRepresentation];
        NSData *jpeg = [bitmap representationUsingType:NSBitmapImageFileTypeJPEG properties:@{NSImageCompressionFactor:@.9}];
        if (!jpeg || ![jpeg writeToFile:destination options:NSDataWritingAtomic error:nil]) return 3;
        return 0;
    }
}
