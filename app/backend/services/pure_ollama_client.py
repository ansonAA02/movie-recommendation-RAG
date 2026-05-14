#!/usr/bin/env python3
"""
純 Ollama 客戶端
支持本地和雲端模型
"""

import os
import re
import requests
import time
import asyncio
from typing import Dict, List, Any, Optional, Mapping

import sys
import os

# 確保可以匯入 services 模組
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

TASK_TIMEOUTS_S = {
    "planner": 12,
    "rule_extraction": 10,
    "chat": 25,
    "explain": 45,
    "compare": 40,
    "insight": 35,
    "default": 30,
}

DEFAULT_LLM_MODEL = "deepseek-r1:671b"
CITATION_RE = re.compile(r"\[E(\d+)\]")


def resolve_llm_model(task_type: Optional[str] = None, requested_model: Optional[str] = None) -> str:
    """Resolve a model name from request override -> task env -> global env -> default."""
    preferred = (requested_model or "").strip()
    if preferred:
        return preferred

    task = str(task_type or "").strip().lower()
    task_env_map = {
        "explain": ["LLM_EXPLAIN_MODEL"],
        "compare": ["LLM_COMPARE_MODEL", "LLM_EXPLAIN_MODEL"],
        "insight": ["LLM_INSIGHT_MODEL", "LLM_EXPLAIN_MODEL"],
        "chat": ["LLM_CHAT_MODEL", "LLM_EXPLAIN_MODEL"],
        "planner": ["AGENT_PLANNER_MODEL", "AGENT_SMALL_MODEL", "AGENT_ROUTER_MODEL"],
        "rule_extraction": ["AGENT_RULES_MODEL", "AGENT_SMALL_MODEL", "AGENT_ROUTER_MODEL"],
    }
    for env_key in task_env_map.get(task, []):
        val = (os.getenv(env_key) or "").strip()
        if val:
            return val

    return (os.getenv("LLM_DEFAULT_MODEL") or DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL


def enforce_sentence_citations(text: str, max_evidence_id: int) -> str:
    """Ensure each non-empty line has valid [E#] citations."""
    if not text:
        return text
    max_id = max(1, int(max_evidence_id))

    def _sanitize_ids(line: str) -> str:
        def _repl(match: re.Match) -> str:
            idx = int(match.group(1))
            return f"[E{idx}]" if 1 <= idx <= max_id else "[E1]"
        return CITATION_RE.sub(_repl, line)

    fixed_lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = _sanitize_ids(line)
        if CITATION_RE.search(line) is None:
            line = f"{line} [E1]"
        fixed_lines.append(line)
    return "\n".join(fixed_lines)


def collect_cited_ids(text: str, max_evidence_id: int) -> List[str]:
    if not text:
        return []
    max_id = max(1, int(max_evidence_id))
    used = set()
    for m in CITATION_RE.finditer(text):
        idx = int(m.group(1))
        if 1 <= idx <= max_id:
            used.add(idx)
    return [f"E{i}" for i in sorted(used)]


def postprocess_explanation(explanation: str, evidence_payload: List[str]) -> Dict[str, Any]:
    """Run citation alignment and return summary metrics."""
    evidence_count = max(1, len(evidence_payload or []))
    fixed = enforce_sentence_citations(explanation or "", max_evidence_id=evidence_count)
    cited_ids = collect_cited_ids(fixed, max_evidence_id=evidence_count)
    all_ids = [f"E{i+1}" for i in range(evidence_count)]
    uncited_ids = [x for x in all_ids if x not in cited_ids]
    citation_alignment_score = float(len(cited_ids) / max(1, len(all_ids)))
    return {
        "explanation": fixed,
        "citations_used": cited_ids,
        "citations_unused": uncited_ids,
        "citation_alignment_score": citation_alignment_score,
    }


def build_explain_inputs(movie: Any, user_ratings: List[Any], request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Build normalized inputs for recommendation explanation generation."""
    raw_question = str((request_payload.get("question") or "")).strip()
    requested_answer_language = str((request_payload.get("answer_language") or "")).strip().lower()
    client_evidence = request_payload.get("evidence") or []
    client_evidence_structured = request_payload.get("evidence_structured") or {}
    client_scores = request_payload.get("scores") or {}
    client_metadata = request_payload.get("movie_metadata") or {}

    user_preferences: Dict[str, Any] = {
        "genres": [],
        "directors": [],
        "actors": [],
        "average_rating": 0.0,
    }

    if user_ratings:
        genre_count: Dict[str, int] = {}
        director_count: Dict[str, int] = {}
        actor_count: Dict[str, int] = {}
        total_rating = 0.0

        for rating in user_ratings:
            total_rating += float(getattr(rating, "rating", 0) or 0)
            rated_movie = getattr(rating, "movie", None)
            if not rated_movie:
                continue

            if float(getattr(rating, "rating", 0) or 0) >= 4.0:
                if getattr(rated_movie, "genres", None):
                    for genre in rated_movie.genres:
                        name = getattr(genre, "name", None)
                        if name:
                            genre_count[name] = genre_count.get(name, 0) + 1

                if getattr(rated_movie, "director", None):
                    director = str(rated_movie.director)
                    director_count[director] = director_count.get(director, 0) + 1

                if getattr(rated_movie, "cast", None):
                    actors = [actor.strip() for actor in str(rated_movie.cast).split(",") if actor.strip()]
                    for actor in actors:
                        actor_count[actor] = actor_count.get(actor, 0) + 1

        top_genres = sorted(genre_count.items(), key=lambda x: x[1], reverse=True)[:3]
        top_directors = sorted(director_count.items(), key=lambda x: x[1], reverse=True)[:3]
        top_actors = sorted(actor_count.items(), key=lambda x: x[1], reverse=True)[:3]

        user_preferences["genres"] = [g for g, _ in top_genres]
        user_preferences["directors"] = [d for d, _ in top_directors]
        user_preferences["actors"] = [a for a, _ in top_actors]
        user_preferences["average_rating"] = total_rating / max(1, len(user_ratings))

    movie_genres = [g.name for g in movie.genres] if getattr(movie, "genres", None) else []
    pref_genres = set(user_preferences.get("genres", []))
    pref_directors = set(user_preferences.get("directors", []))
    pref_actors = set(user_preferences.get("actors", []))

    derived_evidence: List[str] = []
    overlap_genres = sorted(set(movie_genres) & pref_genres)
    if overlap_genres:
        derived_evidence.append(f"Overlaps with your frequent genres: {', '.join(overlap_genres[:3])}")

    if getattr(movie, "director", None) and movie.director in pref_directors:
        derived_evidence.append(f"Director match: {movie.director} is one of your frequently watched creators")

    if getattr(movie, "cast", None):
        cast_overlap = [
            a.strip()
            for a in str(movie.cast).split(",")
            if a.strip() and a.strip() in pref_actors
        ]
        if cast_overlap:
            derived_evidence.append(f"Cast match: includes actors you like: {', '.join(cast_overlap[:3])}")

    if getattr(movie, "year", None):
        preferred_years = set(user_preferences.get("preferred_years", []))
        if movie.year in preferred_years:
            derived_evidence.append(f"年份 {movie.year} 與你最近常看的年代相符")

    combined_scores = {
        "ann": client_scores.get("ann") or client_scores.get("ANN"),
        "kg": client_scores.get("kg") or client_scores.get("KG"),
        "gnn": client_scores.get("gnn") or client_scores.get("GNN"),
        "combined": client_scores.get("combined") or client_scores.get("score"),
    }

    evidence_payload: List[str] = []
    evidence_payload.extend(derived_evidence)
    evidence_payload.extend([str(item) for item in client_evidence if isinstance(item, str) and item.strip()])

    if isinstance(client_evidence_structured, dict) and client_evidence_structured:
        try:
            shared_genres = client_evidence_structured.get("shared_genres") or []
            shared_actors = client_evidence_structured.get("shared_actors") or []
            shared_director = client_evidence_structured.get("shared_director")
            if isinstance(shared_genres, list) and shared_genres:
                evidence_payload.append(f"共享類型（結構化）：{', '.join([str(x) for x in shared_genres[:5]])}")
            if isinstance(shared_actors, list) and shared_actors:
                evidence_payload.append(f"共享演員（結構化）：{', '.join([str(x) for x in shared_actors[:5]])}")
            if shared_director:
                evidence_payload.append(f"共享導演（結構化）：{shared_director}")

            kg = client_evidence_structured.get("kg") or {}
            if isinstance(kg, dict) and kg:
                src = kg.get("source")
                if src:
                    evidence_payload.append(f"KG來源（結構化）：{src}")
                j = kg.get("jaccard")
                if j is not None:
                    try:
                        evidence_payload.append(f"KG鄰居重疊 Jaccard（結構化）：{float(j):.3f}")
                    except Exception:
                        pass
                sim = kg.get("similar_to")
                ref_id = kg.get("sim_ref_movie_id")
                ref_title = kg.get("sim_ref_title")
                if sim is not None:
                    try:
                        simf = float(sim)
                        if simf > 0:
                            ref_str = ""
                            if ref_id:
                                ref_str = f"（參考歷史電影 {ref_id}{f'：{ref_title}' if ref_title else ''}）"
                            evidence_payload.append(f"Neo4j SIMILAR_TO（結構化）：{simf:.3f}{ref_str}")
                    except Exception:
                        pass
        except Exception:
            pass

    seen = set()
    deduped: List[str] = []
    for x in evidence_payload:
        x = (x or "").strip()
        if not x or x in seen:
            continue
        seen.add(x)
        deduped.append(x)
    evidence_payload = deduped[:20]

    question = raw_question or f"Why are you recommending '{getattr(movie, 'title', 'this movie')}' to me? Please use evidence from my history."
    answer_language = "english" if requested_answer_language in {"en", "english"} else "chinese_traditional"

    movie_context = {
        "title": getattr(movie, "title", None),
        "year": getattr(movie, "year", None),
        "genres": movie_genres,
        "director": getattr(movie, "director", None),
        "cast": getattr(movie, "cast", None),
        "description": getattr(movie, "description", None),
    }
    if isinstance(client_metadata, dict):
        movie_context.update(client_metadata)

    return {
        "question": question,
        "answer_language": answer_language,
        "movie_context": movie_context,
        "user_preferences": user_preferences,
        "evidence_payload": evidence_payload,
        "combined_scores": combined_scores,
    }


class PureOllamaClient:
    """純 Ollama 客戶端 (現已改為使用 DeepSeek 官方 API)"""
    
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        # Initialize DeepSeek API
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "dummy-api-key")
        self.base_url = "https://api.deepseek.com"
        # Initialize the OpenAI client for DeepSeek API
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except ImportError:
            self.client = None

    def _resolve_timeout_s(self, task_type: Optional[str], timeout_s: Optional[float]) -> float:
        # Resolve timeout based on task type
        if isinstance(timeout_s, (int, float)) and float(timeout_s) > 0:
            return float(timeout_s)
        if task_type:
            return float(TASK_TIMEOUTS_S.get(str(task_type).strip().lower(), TASK_TIMEOUTS_S["default"]))
        return float(TASK_TIMEOUTS_S["default"])
    
    def is_available(self) -> bool:
        """檢查服務是否可用"""
        # Check if the DeepSeek API client is initialized
        return self.client is not None
    
    def list_models(self) -> List[Dict[str, Any]]:
        """列出可用的模型"""
        # Return the available DeepSeek model
        return [{
            "name": "deepseek-v4-pro",
            "size": 0,
            "modified_at": "",
            "is_cloud": True
        }]
    
    def generate(self, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """生成文本"""
        task_type = str(kwargs.get("task_type") or "default").strip().lower()
        timeout_s = self._resolve_timeout_s(task_type, kwargs.get("timeout_s"))
        
        try:
            start_time = time.time()
            # Call the DeepSeek API using OpenAI SDK
            from openai import OpenAI
            client = OpenAI(
                api_key=os.environ.get('DEEPSEEK_API_KEY') or self.api_key,
                base_url="https://api.deepseek.com"
            )
            
            response = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "user", "content": prompt},
                ],
                stream=False,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}}
            )
            
            response_time = time.time() - start_time
            text = response.choices[0].message.content
            
            return {
                "success": True,
                "text": text,
                "model": "deepseek-v4-pro",
                "task_type": task_type,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "response_time": response_time,
                "timeout_s": timeout_s,
                "is_cloud": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": "deepseek-v4-pro",
                "task_type": task_type,
                "timeout_s": timeout_s,
                "response_time": time.time() - start_time,
            }

    async def agenerate(self, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Async wrapper so FastAPI endpoints don't block the event loop."""
        return await asyncio.to_thread(self.generate, model, prompt, **kwargs)
    
    def generate_recommendation_explanation(
        self,
        movie_context: Dict[str, Any],
        user_preferences: Dict[str, Any],
        question: str,
        evidence: Optional[List[str]] = None,
        scores: Optional[Dict[str, Any]] = None,
        model: str = "deepseek-r1:671b",
    ) -> str:
        """Backward-compatible wrapper returning explanation text only."""
        result = self.generate_recommendation_explanation_with_meta(
            movie_context=movie_context,
            user_preferences=user_preferences,
            question=question,
            evidence=evidence,
            scores=scores,
            model=model,
        )
        return (result.get("text") or "").strip()

    def generate_recommendation_explanation_with_meta(
        self,
        movie_context: Dict[str, Any],
        user_preferences: Dict[str, Any],
        question: str,
        answer_language: str = "chinese_traditional",
        evidence: Optional[List[str]] = None,
        scores: Optional[Dict[str, Any]] = None,
        model: str = "deepseek-r1:671b",
    ) -> Dict[str, Any]:
        """Generate a grounded explanation with evidence citations; returns meta for benchmarking/debug."""

        evidence = evidence or []
        scores = scores or {}

        movie_title = movie_context.get("title", "Unknown Movie")
        movie_genres = ", ".join(movie_context.get("genres", []) or [])
        movie_director = movie_context.get("director") or "Unknown"
        movie_year = movie_context.get("year") or "N/A"
        movie_cast = movie_context.get("cast") or ""
        movie_description = movie_context.get("description") or ""

        # Number evidence for strict citations: [E1], [E2], ...
        if evidence:
            evidence_block = "\n".join([f"- [E{i+1}] {item}" for i, item in enumerate(evidence[:20])])
        else:
            evidence_block = "- [E1] (No extra evidence provided. If you cannot infer from given info, say what's missing.)"
        score_block = ", ".join(
            [
                f"{label}: {value:.2f}"
                for label, value in [
                    ("ANN similarity", scores.get("ann")),
                    ("KG relation", scores.get("kg")),
                    ("GNN structure", scores.get("gnn")),
                    ("Combined", scores.get("combined")),
                ]
                if value is not None
            ]
        ) or "ANN similarity: N/A, KG relation: N/A, GNN structure: N/A"

        language_instruction = (
            "請用「繁體中文」回答。"
            if answer_language != "english"
            else "Please answer in English."
        )

        prompt = f"""
你是電影推薦助理，{language_instruction}語氣自然、像真人朋友在推薦電影。
只能根據提供的資料回答，不可杜撰不存在的事實。

回答目標：
1) 直接回答「為什麼推薦這部片給你」。
2) 優先提到與使用者偏好的連結（類型/導演/演員/年份等）。
3) 內容要精簡、好讀，不要官腔。

引用規則：
- 重要判斷後面加上證據標記，例如 [E1]、[E2]。
- 不需要每句都引用，但至少 2 個關鍵理由要有引用。
- 若證據不足，請坦白說明「目前證據不足」，並指出缺什麼資料。

使用者問題：
{question}

電影資訊：
- 片名：{movie_title} ({movie_year})
- 類型：{movie_genres}
- 導演：{movie_director}
- 演員：{movie_cast}
- 劇情摘要：{movie_description}

使用者偏好：
- 常看類型：{', '.join(user_preferences.get('genres', []))}
- 常看導演：{', '.join(user_preferences.get('directors', []))}
- 常看演員：{', '.join(user_preferences.get('actors', []))}
- 平均評分傾向：{user_preferences.get('average_rating', 0):.1f}/5

可用證據：
{evidence_block}

分數資訊：
{score_block}

輸出格式（固定）：
- 第 1 段：2-3 句自然語言解釋（像真人推薦）。
- 第 2 段：1-2 句「你可以怎樣看這部片」的小建議。
"""
        result = self.generate(model, prompt, max_tokens=320, temperature=0.7, task_type="explain")
        
        if result.get("success"):
            return {"success": True, "text": (result.get("text") or "").strip(), "error": None, "model": model}

        # Fallback: deterministic grounded explanation (still cites evidence), so demos don't fail.
        err = str(result.get("error") or "unknown_error")
        fallback = self._fallback_grounded_explanation(
            question=question,
            movie_title=movie_title,
            movie_year=str(movie_year),
            movie_genres=movie_genres,
            movie_director=movie_director,
            evidence=evidence[:20],
            scores=scores,
        )
        return {"success": False, "text": fallback, "error": err, "model": model}

    async def agenerate_recommendation_explanation_with_meta(
        self,
        movie_context: Dict[str, Any],
        user_preferences: Dict[str, Any],
        question: str,
        answer_language: str = "chinese_traditional",
        evidence: Optional[List[str]] = None,
        scores: Optional[Dict[str, Any]] = None,
        model: str = "deepseek-r1:671b",
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_recommendation_explanation_with_meta,
            movie_context,
            user_preferences,
            question,
            answer_language,
            evidence,
            scores,
            model,
        )

    def _fallback_grounded_explanation(
        self,
        question: str,
        movie_title: str,
        movie_year: str,
        movie_genres: str,
        movie_director: str,
        evidence: List[str],
        scores: Mapping[str, Any],
    ) -> str:
        """Rule-based fallback explanation that always follows the citation contract."""
        ev_lines = [e.strip() for e in (evidence or []) if isinstance(e, str) and e.strip()]
        if not ev_lines:
            ev_lines = ["No evidence provided by the retriever."]
        # Always cite at least E1
        top = ev_lines[:5]
        bullets = "\n".join([f"- {line} [E{i+1}]" for i, line in enumerate(top)])

        ann = scores.get("ann")
        kg = scores.get("kg")
        gnn = scores.get("gnn")
        combined = scores.get("combined")
        score_parts = []
        for k, v in [("ANN", ann), ("KG", kg), ("GNN", gnn), ("Combined", combined)]:
            if v is None:
                continue
            try:
                score_parts.append(f"{k}={float(v):.2f}")
            except Exception:
                pass
        score_line = (", ".join(score_parts) + " [E1]") if score_parts else "[E1]"

        text = (
            f"我會推薦《{movie_title}》({movie_year})，主要因為它和你過去偏好的重合度高，"
            f"而且檢索證據與相似度分數都支持這個判斷。[E1]\n"
            f"就題材與創作班底來看，它在你常看的路線上，命中機率會比較高。[E1]\n\n"
            f"關鍵證據：\n{bullets}\n"
            f"分數摘要：{score_line}\n\n"
            f"建議你把它當作下一部「穩定命中偏好」的選擇；"
            f"如果你最近想看 {movie_genres or '同類型作品'}，這部會是安全又不無聊的一部。[E1]"
        )
        return text
    
    def generate_movie_comparison(self, movie1: str, movie2: str, 
                                model: str = "deepseek-r1:671b") -> str:
        """生成電影比較"""
        
        prompt = f"""
Compare the following two movies in ENGLISH ONLY:

Movie 1: {movie1}
Movie 2: {movie2}

Briefly (<= 150 words) cover:
1) genre/style, 2) target audience, 3) when to recommend, 4) viewing tips.
"""
        
        result = self.generate(model, prompt, max_tokens=300, temperature=0.7, task_type="compare")
        
        if result["success"]:
            return result["text"].strip()
        else:
            return f"抱歉，無法生成電影比較：{result['error']}"

    async def agenerate_movie_comparison(
        self,
        movie1: str,
        movie2: str,
        model: str = "deepseek-r1:671b",
    ) -> str:
        return await asyncio.to_thread(self.generate_movie_comparison, movie1, movie2, model)
    
    def generate_user_insights(self, user_ratings: List[Dict], 
                             model: str = "deepseek-r1:671b") -> str:
        """生成用戶洞察"""
        
        if not user_ratings:
            return "You have no ratings yet. Rate some movies to get personalized insights!"
        
        # 分析用戶評分數據
        genres = {}
        directors = {}
        years = {}
        total_rating = 0
        
        for rating in user_ratings:
            movie = rating.get('movie', {})
            score = rating.get('rating', 0)
            total_rating += score
            
            # 統計類型
            for genre in movie.get('genres', []):
                genre_name = genre.name if hasattr(genre, 'name') else genre
                genres[genre_name] = genres.get(genre_name, 0) + score
            
            # 統計導演
            director = movie.get('director', '')
            if director:
                directors[director] = directors.get(director, 0) + score
            
            # 統計年份
            year = movie.get('year', 0)
            if year:
                years[year] = years.get(year, 0) + score
        
        # 找出最喜歡的類型、導演、年份
        top_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:3]
        top_directors = sorted(directors.items(), key=lambda x: x[1], reverse=True)[:3]
        top_years = sorted(years.items(), key=lambda x: x[1], reverse=True)[:3]
        
        prompt = f"""
Based on the user's viewing history, analyze preferences. Respond in ENGLISH ONLY.

Stats:
- Total ratings: {len(user_ratings)}
- Average rating given: {total_rating / len(user_ratings):.1f}/5

Top preferences:
- Genres: {', '.join([g[0] for g in top_genres])}
- Directors: {', '.join([d[0] for d in top_directors])}
- Years: {', '.join([str(y[0]) for y in top_years])}

Produce a concise insight (<= 200 words): 1) preference summary, 2) recommendations, 3) viewing habits.
"""
        
        result = self.generate(model, prompt, max_tokens=400, temperature=0.8, task_type="insight")
        
        if result["success"]:
            return result["text"].strip()
        else:
            return f"抱歉，無法生成用戶洞察：{result['error']}"

    async def agenerate_user_insights(
        self,
        user_ratings: List[Dict],
        model: str = "deepseek-r1:671b",
    ) -> str:
        return await asyncio.to_thread(self.generate_user_insights, user_ratings, model)
    
    def chat(self, message: str, model: str = "deepseek-r1:671b") -> str:
        """聊天對話"""
        
        prompt = f"""
You are a professional movie recommendation assistant.
User message: {message}

Reply in ENGLISH ONLY with friendly, practical guidance.
"""
        
        result = self.generate(model, prompt, max_tokens=300, temperature=0.7, task_type="chat")
        
        if result["success"]:
            return result["text"].strip()
        else:
            return f"抱歉，我現在無法回答您的問題：{result['error']}"

    async def achat(self, message: str, model: str = "deepseek-r1:671b") -> str:
        return await asyncio.to_thread(self.chat, message, model)

# 全局實例
pure_ollama_client = PureOllamaClient()

def get_pure_ollama_client():
    """獲取純 Ollama 客戶端"""
    return pure_ollama_client

def test_pure_ollama():
    """測試純 Ollama 客戶端"""
    print("🧪 測試純 Ollama 客戶端...")
    
    client = get_pure_ollama_client()
    
    # 檢查可用模型
    models = client.list_models()
    print(f"可用模型: {[m['name'] for m in models]}")
    
    # 測試生成
    result = client.generate("deepseek-v4-pro", "你好，請介紹一下電影推薦系統", max_tokens=100)
    
    if result["success"]:
        print(f"✅ 生成成功")
        print(f"模型: {result['model']}")
        print(f"回應: {result['text']}")
        print(f"響應時間: {result['response_time']:.2f}秒")
        print(f"是否雲端: {result['is_cloud']}")
    else:
        print(f"❌ 生成失敗: {result['error']}")

if __name__ == "__main__":
    test_pure_ollama()
