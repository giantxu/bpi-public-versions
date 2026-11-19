// macOS Vision OCR helper. usage: ocr_vision <image.png>
// prints a JSON array of lines: {"t": text, "x","y","w","h": normalized box, origin top-left}
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.recognitionLanguages = ["zh-Hans", "en-US"]
req.usesLanguageCorrection = false
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
var out: [[String: Any]] = []
for o in req.results ?? [] {
    guard let c = o.topCandidates(1).first else { continue }
    let b = o.boundingBox
    out.append(["t": c.string, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
}
let d = try JSONSerialization.data(withJSONObject: out)
print(String(data: d, encoding: .utf8)!)
