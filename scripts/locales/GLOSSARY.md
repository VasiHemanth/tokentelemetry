# Locale glossary & translation rules

Shared constraints for every translation pass over `scripts/locales/parts/`.
Keep the terms below consistent — the overlay swaps whole rendered text nodes,
so an inconsistent term reads as a bug in two different sentences on the same
screen.

## Rules that apply to every language

1. Translate every entry; never copy English through (exception: strings made
   only of product names, code, or file names).
2. Never retype an English key — output is keyed by the entry index `i`.
3. Many entries are **fragments** that sit next to other UI text (starting with
   `—`, or ending mid-sentence like "replaced with"). Preserve that boundary: no
   added or removed terminal punctuation, same number of sentences.
4. Keep verbatim: `TokenTelemetry`, `Hermes`, `Codex`, `Claude Code`, `Copilot`,
   `Cursor`, `Gemini`, `Qwen`, `Grok`, `OpenCode`, `Pi`, `Antigravity`,
   `Ollama`, `llama.cpp`, `vLLM`, `nvidia-smi`, `MEMORY.md`, `USER.md`,
   `kanban.db`, `state.db`, `/goal`, `/loop`, `cron`, backticked content, paths,
   commands, identifiers, numbers, percentages.
5. Register: concise, technical, neutral. No added explanation, no marketing.
6. Fit the UI: prefer the shortest natural phrasing. French runs ~25 % longer
   than English; watch the sidebar and table headers.
7. Interpolated strings (`{count}`, `{agent}`) are excluded upstream — they are
   not in the key list, so nothing to do about them here.

## Names kept in Latin script

`harness` stays `harness` (do not transliterate). Model, product and file names
per rule 4.

## Terms

| English | zh-CN | zh-TW | ja | ko | fr |
| --- | --- | --- | --- | --- | --- |
| agent | 智能体 | 智慧代理 | エージェント | 에이전트 | agent |
| coding agent | 编程代理 | 编码智慧代理 | コーディングエージェント | 코딩 에이전트 | agent de codage |
| session | 会话 | 工作階段 | セッション | 세션 | session |
| token | token | token | トークン | 토큰 | token (never *jeton*) |
| cost | 成本 | 成本 | コスト | 비용 | coût |
| cache | 缓存 | 快取 | キャッシュ | 캐시 | cache |
| model | 模型 | 模型 | モデル | 모델 | modèle |
| local model | 本地模型 | 本機模型 | ローカルモデル | 로컬 모델 | modèle local |
| prompt | 提示词 | 提示詞 | プロンプト | 프롬프트 | prompt |
| transcript | 转录记录 | 文字記錄 | トランスクリプト | 트랜스크립트 | transcript |
| memory (agent files) | 记忆 | 記憶 | メモリ | 메모리 | mémoire |
| dashboard | 仪表盘 | 儀表板 | ダッシュボード | 대시보드 | tableau de bord |
| power draw | 功耗 | 功耗 | 消費電力 | 전력 소비 | consommation électrique |
| carbon footprint | 碳足迹 | 碳足跡 | 炭素フットプリント | 탄소 발자국 | empreinte carbone |
| billing plan | 套餐 | 訂閱方案 | 料金プラン | 요금제 | offre |
| plan mode | 计划模式 | 計畫模式 | プランモード | 플랜 모드 | mode planifié |
| insights | 洞察 | 洞察 | インサイト | 분석 | analyses |
| settings | 设置 | 設定 | 設定 | 설정 | paramètres |
| quota | 配额 | 配额 | 割り当て | 할당량 | quota |
| artifact | 产物 | 產物 | アーティファクト | 아티팩트 | artefact |
| loop | 循环 | 迴圈 | ループ | 루프 | boucle |
| heartbeat | 心跳 | 心跳 | ハートビート | 하트비트 | signal de vie |
| kanban | 看板 | 看板 | カンバン | 칸반 | kanban |
| swarm | swarm | swarm | スワーム | 스웜 | essaim |
| profile | 配置档案 | 設定檔 | プロファイル | 프로필 | profil |
| gateway | 网关 | 閘道器 | ゲートウェイ | 게이트웨이 | passerelle |
| server | 服务器 | 伺服器 | サーバー | 서버 | serveur |
| data | 数据 | 資料 | データ | 데이터 | données |
| user | 用户 | 使用者 | ユーザー | 사용자 | utilisateur |
| UI / interface | 界面 | 介面 | UI | 인터페이스 | interface |
| default | 默认 | 預設 | デフォルト | 기본값 | par défaut |
| support (verb) | 支持 | 支援 | サポート | 지원 | prise en charge |
| search | 搜索 | 搜尋 | 検索 | 검색 | recherche |
| archive | 归档 | 封存 | アーカイブ | 아카이브 | archiver |
| On / Off | 开启 / 关闭 | 開啟 / 關閉 | オン / オフ | 켜짐 / 꺼짐 | activé / désactivé |
| none | 无 | 無 | なし | 없음 | aucun |
| , (list separator) | 、 | 、 | 、 | , | , |

## Style per language

- **zh-TW**: not a mechanical Simplified→Traditional conversion — convert
  characters *and* use Taiwan wording, `" "` → `「 」`, `‘ ’` → `『 』`,
  keep `——`.
- **ja**: descriptions in です・ます調, short labels/headings in 体言止め,
  `" "` → `「 」`.
- **ko**: descriptions in 합니다체, short labels in 명사형 종결,
  `" "` → `「 」`.
- **fr**: vouvoiement, narrow space before `; ! ? :`, `" "` → `« »`,
  no terminal period on labels.
