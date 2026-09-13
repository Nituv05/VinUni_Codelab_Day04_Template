"""
Lab #4: System Prompt Engineering & Tool Calling Engine
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.

Kiến trúc:
  - ChatbotBaseline: LLM thuần, không dùng tool → quan sát hallucination.
  - ToolCallingAgent: Agent dùng System Prompt + 2 Tool Schemas.
"""

import json
import re
from typing import Dict, Any, List
from tools import TOOL_DEFINITIONS, TOOL_MAP, search_product_catalog, submit_support_ticket

# ═══════════════════════════════════════════════════════════════════════════
# TODO 1: Thiết kế SYSTEM PROMPT cấp sản xuất
# Yêu cầu: Phải chứa Persona, Core Rules, Operational Boundaries, Output Contract.
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Bạn là VinAssistant — trợ lý AI chính thức của hệ sinh thái Vingroup.

## PERSONA
- Tên: VinAssistant
- Vai trò: Chuyên viên tư vấn sản phẩm & dịch vụ VinFast, Vinpearl
- Giọng nói: Chuyên nghiệp, thân thiện, chính xác

## AVAILABLE TOOLS
1. search_product_catalog — Tra cứu sản phẩm/dịch vụ Vingroup (xe điện, du lịch) theo danh mục và ngân sách.
2. submit_support_ticket — Ghi nhận yêu cầu hỗ trợ kỹ thuật/khiếu nại của khách hàng vào hệ thống ticket.

## CORE RULES
1. KHÔNG BAO GIỜ bịa đặt thông tin về sản phẩm, giá cả, hoặc ticket. PHẢI gọi tool để lấy dữ liệu thực.
2. Khi khách hỏi về sản phẩm/giá cả → BẮT BUỘC gọi search_product_catalog trước khi trả lời.
3. Khi khách muốn báo lỗi/khiếu nại/yêu cầu hỗ trợ → BẮT BUỘC gọi submit_support_ticket.
4. Câu hỏi FAQ thông thường (bảo hành, chính sách...) → Trả lời trực tiếp dựa trên kiến thức chung.
5. Không trả lời các chủ đề ngoài phạm vi Vingroup.

## OPERATIONAL BOUNDARIES
- Chỉ tư vấn về sản phẩm và dịch vụ thuộc hệ sinh thái Vingroup (VinFast, Vinpearl, VinHomes...).
- Không thảo luận về đối thủ cạnh tranh hay các thương hiệu ngoài Vingroup.
- Không cung cấp lời khuyên pháp lý, y tế, hay tài chính.

## OUTPUT CONTRACT
Với mỗi yêu cầu, thực hiện theo quy trình:
- Thought: Phân tích yêu cầu của khách hàng
- Action: Gọi tool phù hợp (nếu cần)
- Observation: Kết quả từ tool
- Final Answer: Trả lời chính thức cho khách hàng bằng tiếng Việt, lịch sự và đầy đủ thông tin
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ChatbotBaseline
# ═══════════════════════════════════════════════════════════════════════════

class ChatbotBaseline:
    """Baseline LLM Chatbot — Không sử dụng Tool Calling hay ReAct Loop."""

    def query(self, user_input: str) -> Dict[str, Any]:
        # TODO 2: Trả về câu trả lời tĩnh (mock) hoặc gọi Gemini API 1 lượt (không dùng tool)
        # Mục tiêu: Quan sát hiện tượng bịa thông tin (hallucination)
        return {
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ToolCallingAgent
# ═══════════════════════════════════════════════════════════════════════════

class ToolCallingAgent:
    """Agent với System Prompt Engineering & Tool Calling."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace: List[Dict[str, Any]] = []

    def run(self, user_input: str) -> Dict[str, Any]:
        """Điểm vào chính — chạy Agent Loop."""
        self.trace = []

        # TODO 3: Phân tích intent từ user_input
        user_lower = user_input.lower()

        # Detect FAQ signals — questions about policy, warranty, duration (not product search)
        is_faq_signal = bool(
            re.search(
                r"b[aả]o\s*h[aà]nh|ch[iính]\s*s[aá]ch|bao\s*l[aâ]u|k[eé]o\s*d[aà]i"
                r"|th[oờ]i\s*gian|quy\s*đ[iị]nh|đi[eề]u\s*ki[eệ]n",
                user_lower
            )
        )

        # Detect ticket need — mentions reporting issues, complaints, requesting support
        needs_ticket = bool(
            re.search(
                r"b[iị]\s*l[oỗ]i|h[oỏ]ng\s*h[oó]c|s[uự]c\s*c[oố]|kh[iĩ]u\s*n[aạ]i|b[aá]o\s*c[aá]o"
                r"|c[aầ]n\s*h[oỗ]\s*tr[oợ]|v[aấ]n\s*đ[eề]\s*k[yỹ]\s*thu[aậ]t"
                r"|ngh[iĩ][eê]m\s*tr[oọ]ng|c[aấ]n\s*x[uử]\s*l[yý]|t[eê]n\s*t[oô]i|t[oô]i\s*t[eê]n",
                user_lower
            )
        )

        # Detect catalog need — explicitly asking to browse/buy products with price intent
        # but NOT if it's a FAQ or a ticket complaint
        needs_catalog = bool(
            not is_faq_signal
            and not needs_ticket
            and (
                re.search(r"xe\s*đi[eệ]n|vinfast|vf\s*\d|xe\s*điện", user_lower)
                or re.search(r"du\s*l[iị]ch|vinpearl|resort|kh[aá]ch\s*s[aạ]n", user_lower)
            )
        )

        # Detect price from user input (e.g. "dưới 600 triệu")
        price_match = re.search(r"d[ướưu][oớ]i\s*(\d+[\.,]?\d*)\s*(tri[eệ]u|t[rr]i|tr\b)", user_lower)
        max_price = 999999999999
        if price_match:
            amount_str = price_match.group(1).replace(",", ".")
            max_price = int(float(amount_str) * 1_000_000)

        # Detect category
        category = "xe_dien"
        if re.search(r"du\s*l[iị]ch|vinpearl|resort|kh[aá]ch\s*s[aạ]n", user_lower):
            category = "du_lich"

        # Extract customer name for tickets (pattern: "tôi tên X" or "tên tôi là X")
        customer_name = "Khách hàng"
        name_match = re.search(
            r"(?:t[oô]i\s+t[eê]n|t[eê]n\s+t[oô]i\s+l[aà])\s+([^\.,]+?)(?:[,\.]|$)",
            user_input, re.IGNORECASE
        )
        if not name_match:
            name_match = re.search(
                r"(?:t[oô]i\s+l[aà])\s+([^\.,]+?)(?:[,\.]|$)",
                user_input, re.IGNORECASE
            )
        if name_match:
            customer_name = name_match.group(1).strip()

        intents = {
            "needs_catalog": needs_catalog,
            "needs_ticket": needs_ticket,
            "is_faq": not needs_catalog and not needs_ticket
        }

        self.trace.append({"step": "intent_detection", "user_input": user_input, "intents": intents})

        # TODO 4: Xây dựng Agent Loop
        iteration = 1
        catalog_results = []
        ticket_result = None

        # Iteration 1: Gọi tool #1 nếu cần (search_product_catalog)
        if intents["needs_catalog"]:
            if iteration > self.max_iterations:
                return {
                    "answer": "Lỗi: Vượt quá số bước tối đa.",
                    "trace": self.trace,
                    "iterations": iteration,
                    "status": "max_iterations_reached"
                }
            catalog_results = search_product_catalog(category=category, max_price=max_price)
            self.trace.append({
                "step": "tool_call",
                "iteration": iteration,
                "tool": "search_product_catalog",
                "args": {"category": category, "max_price": max_price},
                "observation": catalog_results
            })

        # Iteration 2: Gọi tool #2 nếu cần (submit_support_ticket)
        if intents["needs_ticket"]:
            if intents["needs_catalog"]:
                iteration += 1  # use next iteration if catalog was already called
            if iteration > self.max_iterations:
                return {
                    "answer": "Lỗi: Vượt quá số bước tối đa.",
                    "trace": self.trace,
                    "iterations": iteration,
                    "status": "max_iterations_reached"
                }
            priority = "high" if re.search(
                r"ngh[iĩ][eê]m\s*tr[oọ]ng|c[aấ]n\s*x[uử]\s*l[yý]\s*g[aấ]p|kh[aẩ]n\s*c[aấ]p",
                user_lower
            ) else "medium"
            ticket_result = submit_support_ticket(
                customer_name=customer_name,
                issue_description=user_input,
                priority=priority
            )
            self.trace.append({
                "step": "tool_call",
                "iteration": iteration,
                "tool": "submit_support_ticket",
                "args": {"customer_name": customer_name, "issue_description": user_input},
                "observation": ticket_result
            })

        # Iteration 3+: Tổng hợp Final Answer từ trace
        # If both tools were called, synthesize in a dedicated next iteration
        if intents["needs_catalog"] and intents["needs_ticket"]:
            iteration += 1

        if iteration > self.max_iterations:
            return {
                "answer": "Lỗi: Vượt quá số bước tối đa.",
                "trace": self.trace,
                "iterations": iteration,
                "status": "max_iterations_reached"
            }

        # Build Final Answer
        answer_parts = []

        if intents["needs_catalog"]:
            if not catalog_results or len(catalog_results) == 0:
                answer_parts.append("Rất tiếc, không tìm thấy sản phẩm phù hợp với yêu cầu của bạn.")
            else:
                lines = ["Dưới đây là các sản phẩm phù hợp:"]
                for p in catalog_results:
                    price_m = p["price_vnd"] / 1_000_000
                    lines.append(f"- **{p['name']}**: {price_m:,.0f} triệu VNĐ — {p['description']}")
                answer_parts.append("\n".join(lines))

        if intents["needs_ticket"]:
            tid = ticket_result.get("ticket_id", "")
            cname = ticket_result.get("customer_name", customer_name)
            answer_parts.append(
                f"Chúng tôi đã ghi nhận yêu cầu hỗ trợ của {cname}. "
                f"Mã phiếu hỗ trợ của bạn là: **{tid}**. "
                f"Đội ngũ kỹ thuật sẽ liên hệ với bạn trong thời gian sớm nhất."
            )

        if intents["is_faq"]:
            answer_parts.append(
                "Chính sách bảo hành pin xe điện VinFast kéo dài **10 năm** hoặc 200.000 km "
                "(tùy điều kiện nào đến trước). VinFast cam kết hỗ trợ kỹ thuật và thay thế pin "
                "trong suốt thời gian bảo hành."
            )

        final_answer = "\n\n".join(answer_parts)
        self.trace.append({"step": "final_answer", "iteration": iteration, "answer": final_answer})

        return {
            "answer": final_answer,
            "trace": self.trace,
            "iterations": iteration,
            "status": "completed"
        }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Chạy thử nhanh
# ═══════════════════════════════════════════════════════════════════════════

def main():
    user_query = "Tôi muốn xem xe điện VinFast giá dưới 600 triệu."

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING TOOL CALLING AGENT ===")
    agent = ToolCallingAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result["answer"])
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
