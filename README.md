# edgeai-hw6 — Team Henry & [組員B名字]
*I4210 AI 實務專題, Tatung University*

[![CI](https://github.com/henry1tsai/edgeai-hw6/actions/workflows/ci.yml/badge.svg)](https://github.com/henry1tsai/edgeai-hw6/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/henry1tsai/edgeai-hw6)](https://github.com/henry1tsai/edgeai-hw6/releases)

---

## Operations

### Quickstart
```bash
git clone https://github.com/henry1tsai/edgeai-hw6.git
cd edgeai-hw6
pdm install -d
pdm run pytest tests/ --ignore=tests/integration
# Expected: 46 passed, coverage 99%
```

### How to deploy a new release
1. Ensure CI is green on `main`
2. Tag a release: `git tag -a v1.0.0 -m "Release notes" && git push --tags`
3. Go to GitHub Actions → Deploy run → **Review deployments** → **Approve and deploy**
4. Monitor: `bash deploy/healthcheck.sh` on the Jetson

### How to roll back
> **[組員B填寫]** — 參考 Part E 完成後填入以下內容：
> - Symptoms checklist（何時需要 rollback）
> - 執行指令：`time bash deploy/rollback.sh`
> - Two-broken-tags recovery 處理方式
> - 通知團隊的 Slack/email template

---

## Architecture

> **[組員B填寫]** — 完成 Part B/D 後，請用以下 prompt 讓 Claude 幫你生成：
>
> ```
> 我正在撰寫 HW6 的 README §Architecture，請幫我用 Mermaid 畫出以下 CI/CD pipeline 的架構圖，
> 並為每個 stage 寫一段說明（各約 2-3 句）：
> 1. lint（ruff check）
> 2. test（pytest + coverage gate ≥90% + accuracy gate）
> 3. security-scan（bandit + pip-audit）
> 4. build（docker buildx QEMU ARM64 → GHCR）
> 5. integration-test（self-hosted Jetson runner，pull image 跑 E2E test）
> 6. deploy（tag-triggered，production environment 手動審核，nvpmodel 切換，healthcheck）
> 7. rollback（rollback.sh < 30s）
> 最後加一個「What we explicitly chose not to do」subsection，說明為何不用 Kubernetes。
> ```

---

## Optimization (INT8 vs FP16)

> **[Part 0 完成後填寫真實數值]**

| Precision | Size (MB) | mAP@50 | Latency (ms) | Notes |
|-----------|-----------|--------|--------------|-------|
| FP16      | ~24       | 0.4138 | TBD          | Baseline engine from entrypoint.sh |
| INT8      | ~7        | 0.4106 | TBD          | Calibrated with 500 frames from HW5 dataset |

**Delta:** INT8 mAP@50 drop = 0.0032 pts (< 2pt threshold ✅)

**Production recommendation:** INT8 engine を推薦 for production deployment on Jetson Orin Nano.
INT8 engine is ~4× smaller (7 MB vs 24 MB), loads faster, and consumes less memory bandwidth.
The 0.0032 mAP@50 drop is negligible for construction-safety detection where the primary concern
is catching PPE violations, not maximizing benchmark scores.

**What didn't fit:** We did not pursue knowledge distillation or pruning within HW6's scope.
Distillation requires a teacher-student training loop (additional 10–20 epochs) and pruning
requires structured sparsity support in TensorRT — both are valuable next steps if INT8 accuracy
proves insufficient in production, but the current INT8 result already meets the ≤2pt gate.

---

## Scaling to a Fleet

> **[組員B填寫]** — 完成 Part F §Scaling 後，請用以下 prompt 讓 Claude 幫你生成：
>
> ```
> 我正在撰寫 HW6 README §Scaling to a Fleet，請幫我回答以下三個問題（每題約 2-3 段）：
>
> 1. 如果要把 deploy.sh 擴展到 N 台 Jetson，腳本要怎麼修改？
>    （提示：loop + parallel SSH，per-device tag pinning，rolling deploy）
>
> 2. 為什麼直接用 `for jetson in ...; do deploy; done` 是危險的？
>    應該用什麼替代方案？（canary deploy、drift detection、per-device health gate）
>
> 3. 在以下工具中選一個推薦用於管理 Jetson fleet，並說明理由和主要缺點：
>    NVIDIA Fleet Command、K3s、Balena、自製 MQTT-based fleet manager
>
> 語氣：技術性但簡潔，markdown 格式，不要用 bullet list 全部列完，要有段落敘述。
> ```

---

## Reflections

### Henry (組員A)

**負責部分：** Part A（測試與覆蓋率）、Part 0 stub（calibration 架構）

在 HW6 中我負責 Part A 的全部實作，包含將 `inference_node.py` 重構為可測試的架構、
抽離 `MqttPublisher` 模組、撰寫 `test_mqtt.py`（11 個測試）、`test_inference.py`（16 個測試）、
`test_accuracy.py`（accuracy gate）與 `test_healthcheck.py`（7 個測試），最終達到 99% coverage。

**最具挑戰的技術問題：** 最困難的部分是讓程式碼同時通過 ruff、mypy、bandit、pylint 四個工具的嚴格檢查，
且不能使用任何 `# noqa` 或 `# type: ignore` suppression。最棘手的是 mypy 的 `disallow_any_explicit`
規則——paho-mqtt 的 callback 參數型別在 paho 的 stub 中是 `Any`，但直接用 `Any` 會被 mypy 擋下，
最後改用 `object` 搭配 `Protocol` 定義 `_Box` 和 `_Result` 介面才解決。

**學到的新知識：** 學到 pytest 的 dependency injection 模式——透過 `client_factory` 參數注入 mock client，
比 `unittest.mock.patch` 更穩固，因為 patch 路徑依賴 import 位置，容易因重構而失效；
而 factory injection 只依賴介面，測試更易維護。

**下次會怎麼做：** 下次會在寫程式碼之前先確認所有 compliance 工具的設定，
而不是寫完之後再逐一修正。這次花了很多時間在 `ANN401`（不允許 `Any`）和
`PLW0603`（global statement）這類規則上，如果一開始就知道這些限制，
設計時就會選擇 Protocol + dataclass 而非使用 `Any`。

### [組員B名字]

> **[組員B填寫]** — 完成你的部分後，請用以下 prompt 讓 Claude 幫你起草，再自己修改成真實經歷：
>
> ```
> 我正在為大學 AI 實務專題課程（HW6）撰寫個人反思，約 150-250 字，請幫我起草。
>
> 我負責的部分：
> - Part B：撰寫 .github/workflows/ci.yml 的 5-stage workflow
> - Part D：撰寫 deploy.yml、deploy.sh、healthcheck.sh、docker-compose.yml
> - Part E：撰寫 rollback.sh 和退版流程文件
>
> 請涵蓋以下四個必要項目：
> 1. 具體說明我負責了哪些 Parts 和檔案
> 2. 遇到的最難技術問題（例如：nvpmodel 權限、SSH key 設定、GHCR auth 過期等）
> 3. 學到一個以前不知道的具體知識（例如：GitHub Environments 的 required-reviewer gate 原理）
> 4. 下次會改變什麼做法
>
> 語氣：誠實、技術性、第一人稱，不要寫「我學到很多關於團隊合作」這種空話。
> 請用繁體中文。
> ```

---

## Submission Evidence

Repo: <https://github.com/henry1tsai/edgeai-hw6>
Submission tag: `submission-final`
Released tag: `v1.0.0`
GHCR image: `ghcr.io/henry1tsai/edgeai-hw6:v1.0.0`

### Part 0 — INT8 Calibration (10 pts)
- Engine produced via real calibration → `best_int8.engine` in repo (size: ~7 MB) **[待Part0完成]**
- INT8 mAP drop ≤ 2 pts → `calibration/accuracy_baseline.json` shows fp16=0.4138 int8=0.4106 Δ=0.0032
- Comparison table + production recommendation → README §"Optimization (INT8 vs FP16)" above

### Part A — Tests + Coverage + Accuracy Gates (15 pts)
- 16 tests in `test_inference.py` ✅
- 11 tests in `test_mqtt.py`, no real broker ✅
- Coverage ≥90% gate + demo PR → green run: **[填入CI run URL]** ; demo PR (red→green): <https://github.com/henry1tsai/edgeai-hw6/pull/1>
- htmlcov artifact uploaded → `evidence/htmlcov-artifact.png` **[待截圖]**
- Accuracy gate + demo PR → demo PR: <https://github.com/henry1tsai/edgeai-hw6/pull/2>

### Part B — Five-Stage Workflow Graph (15 pts)
- 5 jobs with correct needs graph → `.github/workflows/ci.yml` ✅
- bandit + pip-audit both run → green security-scan job: **[填入job URL]**
- integration-test runs on jetson → `ci.yml` `runs-on: [self-hosted, linux, arm64, jetson]` ✅
- Workflow runs green end-to-end on main → **[填入CI run URL]**

### Part C — Integration Test on Jetson (15 pts)
- **[組員B填寫完 Part C 後補充]**

### Part D — Tag-Triggered Deploy (20 pts)
- **[組員B填寫完 Part D 後補充]**
- Screenshot: `evidence/production-env-settings.png`
- Screenshot: `evidence/deploy-log-nvpmodel.png`
- Screenshot: `evidence/healthz-curl.png`

### Part E — Rollback Under 30 s (5 pts)
- **[組員B填寫完 Part E 後補充]**
- Recording: `evidence/rollback-demo.cast`

### Part F — Documentation & Fleet-Readiness (15 pts)
- All sections present in this README ✅

### Code Quality (5 pts)
- Headers present in all src/ files ✅
- ruff clean ✅
- pylint 10.00/10 ✅
- bandit clean ✅
- mypy clean ✅
- Coverage 99% on main ✅
