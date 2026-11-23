# Research report: EmbeddingGemma 2 on Ollama, cloud embedding APIs, non-Ollama runtimes (as of 2026-11-22)

I fetched primary pages where I could, but the fetch tool summarizes pages, so exact strings are only as good as that summary. "Unverified" marks anything I could not confirm. No code was changed.

## 1. Ollama and EmbeddingGemma 2

**Tags and sizes** ([ollama.com/library/embeddinggemma-2](https://ollama.com/library/embeddinggemma-2)):

| Tag | Download | Input modalities |
|---|---|---|
| `270m` | 304 MB to 378 MB | text |
| `440m` | 671 MB to 714 MB | text + image |
| `570m` | 918 MB to 990 MB | text |
| `740m` | 1.3 GB | text + image |
| `latest` | 1.3 GB | text + image |

- The size ranges come from the tag table. The 440m tag page ([ollama.com/library/embeddinggemma-2:440m](https://ollama.com/library/embeddinggemma-2:440m)) shows 671 MB as a 304 MB Q8_0 text model plus a 367 MB F16 vision projector, and 714 MB as a second entry.
- The model card says 570m is text + audio and 740m is text + audio + image + video ([model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)). Ollama lists 570m as text only, and 740m as text and image.
- **Output dimension:** the native dimension is 768. Matryoshka sizes are 128, 256, 512 and 768, and truncated vectors should be re-normalized ([Ollama page](https://ollama.com/library/embeddinggemma-2), [model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)).
- **Max input tokens:** 8,192, shared across all modalities. That is roughly 29 images at 280 tokens each ([model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)). The Ollama tag table says "256K", which conflicts with the 8K on the same site and the model card. Treat 8,192 as correct; the 256K is likely a page template error (unverified).
- **Does `/api/embed` accept images?** Yes, per Ollama's API doc ([docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md)).
  - `input` may be a string, a list of strings, or objects `{"text": "...", "image": "<base64>"}` or `{"image": "<base64>"}`. Lists can mix plain strings and objects.
  - The image is raw base64 bytes, not a data URI. `audio` takes the same form. `video` is not accepted.
  - Other fields are `truncate` (default true), `options`, `keep_alive` and `dimensions`.
  - The image form is documented, but I did not test it against a real 440m or 740m pull. Treat the exact payload as unverified until a live call is made.
- **Minimum Ollama version:** not stated on the library pages. A third-party blog claims v0.11.10 for the original EmbeddingGemma ([search result](https://iphonewired.com/jailbreak/1200249/)). That is unverified, and it does not cover the multimodal v2. For the v2 minimum, check the Ollama GitHub releases for the commit that added `image` input to `/api/embed`. I did not find it.
- **Prompt prefixes:** text only. Images, video and audio take no prefix ([HF card](https://huggingface.co/google/embeddinggemma-2), [model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)).
  - Search query: `task: search result | query: {query}`
  - Document: `title: {title} | text: {content}`. Use `title: none` if there is no title.
  - Question answering: `task: question answering | query: {q}`
  - Fact checking: `task: fact checking | query: {claim}`
  - Code retrieval: `task: code retrieval | query: {query}`
  - Symmetric tasks: `task: classification | query: {c}`, `task: clustering | query: {c}`, `task: sentence similarity | query: {c}`
  - Whether Ollama applies any prefix automatically is not documented, so the app must add the prefixes itself (unverified).
- **Are 740m text embeddings identical to 270m?** Unverified. The card says 740m is the 270m text backbone plus 170M vision and 300M audio encoders. Loading text only gives an effective 270M ([model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)). The text weights are probably the same, but no page states the outputs are bit-identical. Ollama's 270m is also Q8_0, which may differ from other builds. For a same-model lock, treat tags as distinct models.
- **Precision warning:** float16 can return NaN or silently degraded embeddings. Use bf16 or fp32 ([model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)).

## 2. Ollama management endpoints

All from [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md). The example version string in that doc is 0.5.1, so it is not a version requirement.

- **`POST /api/pull`**
  - Request: `model`, `insecure`, `stream`.
  - Streaming NDJSON: `{status}`, plus `digest`, `total` and `completed` during layer downloads. `completed` can be absent until a layer finishes.
  - Status sequence: `pulling manifest`, then `pulling <digest>` per layer, then `verifying sha256 digest`, `writing manifest`, `removing any unused layers`, `success`.
  - With `stream: false` you get a single `{"status":"success"}`.
- **`GET /api/version`** returns `{"version": "..."}`.
- **`GET /api/tags`**
  - Returns `models[]` with `name`, `model`, `modified_at`, `size`, `digest` and `details` (`parent_model`, `format`, `family`, `families`, `parameter_size`, `quantization_level`).
  - This is the place to read the digest for the same-model lock.
- **`POST /api/show`**
  - Request: `model`, `verbose`.
  - Returns `modelfile`, `parameters`, `template`, `details`, `model_info` and `capabilities`.
  - The documented response has no top-level digest. `/api/tags` and `/api/ps` carry it.
  - Whether `capabilities` lists an image or vision entry for embedding models is unverified. Check it on a live pull.

## 3. Cloud embedding APIs

| Provider | Endpoint | Images | Response `model` field | Notes |
|---|---|---|---|---|
| OpenAI ([ref](https://developers.openai.com/api/reference/resources/embeddings/methods/create)) | `POST /v1/embeddings` | No | Yes, top level | Request: `model`, `input` (string, list, or token arrays), `dimensions` (text-embedding-3 and later only), `encoding_format` (`float` or `base64`). Response: `object:"list"`, `data[]{object, index, embedding}`, `model`, `usage{prompt_tokens, total_tokens}`. Max 8,192 tokens per input. |
| Gemini ([docs](https://aistudio.google.com/docs/embeddings)) | `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent`, and `:batchEmbedContents` | Yes (`gemini-embedding-2`: PNG and JPEG, max 6 per request) | Not documented in the page I read | Auth is the `x-goog-api-key` header. Body: `content.parts[]` with `text` or `inline_data{mime_type, data(base64)}`, plus `output_dimensionality` (128 to 3072, default 3072). `task_type` is not supported on v2, so put the task prefix in the text. `gemini-embedding-001` is text only. Multiple parts in one content give one aggregated embedding. The raw REST response shape was not shown (unverified). |
| Voyage ([docs](https://docs.voyageai.com/reference/multimodal-embeddings-api)) | `POST https://api.voyageai.com/v1/multimodalembeddings` | Yes (also video) | Yes | Body: `inputs[]{content[]}`, where each piece has `type` (`text`, `image_url`, `image_base64`, ...) and a matching key. Also `model`, `input_type` (`query` or `document`), `truncation`. Models: `voyage-multimodal-3.5` and `voyage-multimodal-3`. Response has `data[]{embedding, index}`, `model`, `usage`. Text-only endpoint `/v1/embeddings`: unverified. |
| Cohere ([docs](https://docs.cohere.com/reference/embed)) | `POST https://api.cohere.com/v2/embed` | Yes, v3 and newer (data URIs; JPEG, PNG, WebP, GIF) | No `model` in the response | Body: `model`, `input_type` (required: `search_document`, `search_query`, `classification`, `clustering`, `image`), `texts`, `images`, or `inputs[]{content[]}`, plus `output_dimension` (v4 and newer) and `embedding_types`. Response: `id`, `embeddings{float:[...]}`, `meta`. The lock cannot be verified from the response, so trust the requested model name. |
| Jina ([jina.ai/embeddings](https://jina.ai/embeddings/)) | `POST https://api.jina.ai/v1/embeddings` | Yes | Not documented on that page (unverified) | The page says it matches the OpenAI schema. Body: `model`, `input[]`, `normalized`, `embedding_type`. Multimodal: items in `input` use an `image`, `audio`, `video` or `pdf` key holding a URL or base64. The exact object shape was not shown. Image models include `jina-embeddings-v4`, `jina-clip-v2` and the v5-omni family. |
| Mistral ([docs](https://docs.mistral.ai/api/endpoint/embeddings)) | `POST /v1/embeddings` | No (text only) | Yes | Body: `model` (`mistral-embed`), `input`, `encoding_format`, `output_dtype`, `output_dimension`. Response: `id`, `object`, `data[]`, `model`, `usage`. The SDK examples use `inputs` while the cURL and schema use `input`. |
| OpenRouter ([docs](https://openrouter.ai/docs/api-reference/embeddings)) | `POST https://openrouter.ai/api/v1/embeddings` | Some models (for example `google/gemini-embedding-2-preview`), via `content[]` with `image_url` | Shown only in the contextual example; verify | `GET /api/v1/embeddings/models` lists models and their `input_modalities`. A gateway can route one slug to different upstream models, so the returned `model` is the best available lock evidence. |
| LiteLLM and other OpenAI-compatible gateways | OpenAI shape | Varies | Unverified | I did not fetch LiteLLM docs. Per-gateway behavior is unverified. |

**Same-model lock approach.**
- Store the requested model, the endpoint host, the dimension and the returned `model` string.
- On a later call, reject a changed returned `model` or a changed vector length.
- For Cohere and possibly Gemini and Jina, the response carries no model name, so the lock can only rest on the configured name and the dimension.

## 4. Running EmbeddingGemma 2 without Ollama

- **Hugging Face repo:** `google/embeddinggemma-2` ([HF](https://huggingface.co/google/embeddinggemma-2)).
  - License is Apache 2.0, and Google states it is open weights ([mixed-news](https://mixed-news.com/en/?p=35813), [model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)).
  - The page did not say whether the repo is gated (unverified). The v1 Gemma license gate was reportedly dropped.
- **transformers and sentence-transformers:** both are supported. `SentenceTransformer("google/embeddinggemma-2")` with `encode(..., prompt_name=...)` and `truncate_dim` in {128, 256, 512} works. `encode()` accepts dicts with `text`, `image` and `video` keys, and placeholders such as `<|image|>`. No minimum transformers version was stated (unverified). Encoders can be disabled through `config_kwargs`. Use bf16 or fp32.
- **GGUF:** [unsloth/embeddinggemma-2-GGUF](https://huggingface.co/unsloth/embeddinggemma-2-GGUF/discussions/4) exists, and [Unsloth's guide](https://unsloth.ai/docs/models/embeddinggemma-2) shows llama.cpp with `--embeddings`. Per that guide, GGUF covers text only. Image, video and audio need a runtime with explicit encoder support.
- **ONNX:** none found for v2. The only hit was `onnx-community/embeddinggemma-300m-ONNX`, which is v1. Unverified for v2.
- **MLX:** none found. Unverified.
- **Other:** a [Core ML build](https://huggingface.co/fluidinference/embeddinggemma-2-coreml) covers text, image and audio. A WebGPU demo space is `webml-community/embeddinggemma-2-webgpu`, mentioned on the [HF page](https://huggingface.co/google/embeddinggemma-2).

## Open items to verify on a live machine

1. The exact `/api/embed` image payload against a real `embeddinggemma-2:440m` pull.
2. The minimum Ollama version, from the GitHub release that added `image` input to `/api/embed`.
3. Whether `/api/show` `capabilities` exposes an image or vision flag for embedding models.
4. Whether 740m text vectors match 270m. Run the same prefixed strings through both and compare cosine similarity.
5. The Gemini, Jina and OpenRouter raw REST response shapes, and whether they include `model`.
