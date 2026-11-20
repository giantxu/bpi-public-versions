// macOS Vision barcode / QR detector. usage: codes_vision <image.png>
// prints a JSON array: {"t": payload, "s": symbology, "x","y","w","h": normalized box, origin top-left}
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("[]"); exit(0) }
let req = VNDetectBarcodesRequest()
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
var out: [[String: Any]] = []
for o in req.results ?? [] {
    let b = o.boundingBox
    out.append(["t": o.payloadStringValue ?? "", "s": o.symbology.rawValue.replacingOccurrences(of: "VNBarcodeSymbology", with: ""),
                "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
}
let d = try JSONSerialization.data(withJSONObject: out)
print(String(data: d, encoding: .utf8)!)
