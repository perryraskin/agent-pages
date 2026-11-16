// Pixel OCR audit: swift examples/showcase/scan.swift docs/images/showcase.png
import Foundation
import Vision
import AppKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
try VNImageRequestHandler(url: url).perform([request])
let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
print(text)
let forbidden = #"(?i)(https?://|localhost|/Users/|/home/|@|\.local\b|\.internal\b|token=|perryraskin)"#
if text.range(of: forbidden, options: .regularExpression) != nil { exit(1) }
