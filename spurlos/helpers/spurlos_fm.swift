// Kleines Hilfsprogramm für Apple Intelligence (Foundation Models, macOS 26+).
// Liest eine Anfrage von der Standardeingabe und gibt die Antwort des Modells auf dem Mac aus.
// Aufruf:  spurlos-fm --check        → prüft, ob das Modell verfügbar ist
//          echo "Text" | spurlos-fm  → Antwort des Modells
import Foundation
import FoundationModels

func fail(_ text: String, _ code: Int32) -> Never {
    FileHandle.standardError.write(Data((text + "\n").utf8))
    exit(code)
}

@main
struct SpurlosFM {
    static func main() async {
        let model = SystemLanguageModel.default
        switch model.availability {
        case .available:
            break
        case .unavailable(let reason):
            fail("unavailable: \(reason)", 2)
        @unknown default:
            fail("unavailable: unknown", 2)
        }
        if CommandLine.arguments.contains("--check") {
            print("available")
            exit(0)
        }
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let prompt = String(decoding: input, as: UTF8.self)
        if prompt.isEmpty { fail("empty prompt", 1) }
        do {
            let session = LanguageModelSession(model: model)
            let response = try await session.respond(to: prompt)
            print(response.content)
        } catch {
            fail("error: \(error)", 1)
        }
    }
}
