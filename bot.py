import requests
from bs4 import BeautifulSoup
import os
import sys

# ================= 설정 부분 =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# 이제 단일 CHAT_ID 환경변수는 사용하지 않고 파일로 관리합니다.
LAST_NUM_FILE = "last_num.txt"
CHAT_IDS_FILE = "chat_ids.txt"
# =============================================

def update_subscribers():
    """새로 봇에게 말을 건 사용자의 Chat ID를 수집하여 파일에 저장합니다."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    
    # 기존 구독자 목록 불러오기
    subscribers = set()
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    subscribers.add(stripped)
    
    # 텔레그램 서버에서 새로운 메시지 확인
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get("ok"):
            for result in data.get("result", []):
                # 메시지를 보낸 사용자의 chat_id 추출
                if "message" in result and "chat" in result["message"]:
                    chat_id = str(result["message"]["chat"]["id"])
                    subscribers.add(chat_id)
                    
        # 갱신된 구독자 목록을 파일에 다시 저장
        with open(CHAT_IDS_FILE, 'w', encoding='utf-8') as f:
            for chat_id in subscribers:
                f.write(chat_id + "\n")
                
        return list(subscribers)
        
    except Exception as e:
        print(f"구독자 업데이트 중 오류 발생: {e}")
        return list(subscribers)

def send_telegram_message(text, chat_ids):
    """여러 사용자(Chat IDs)에게 텔레그램 메시지를 전송합니다."""
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        try:
            requests.post(url, data=payload)
        except Exception as e:
            print(f"Chat ID {chat_id}로 메시지 전송 실패: {e}")

def get_latest_notices():
    """게시판을 크롤링하여 최신 글 목록을 가져옵니다."""
    url = "https://dorm.knu.ac.kr/app/board24"
    latest_posts = []
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('tbody tr')
        
        for row in rows:
            num_element = row.select_one('.td_num2')
            if not num_element:
                continue
                
            num_text = num_element.text.strip()
            if num_text == "공지":
                continue
                
            title_element = row.select_one('.td_subject .bo_tit a')
            title = title_element.text.strip()
            link = title_element['href']
            
            try:
                real_post_id = link.split('/')[-1]
                real_post_id = int(real_post_id.split('?')[0])
            except ValueError:
                continue
            
            latest_posts.append({
                'number': real_post_id,
                'title': title,
                'link': link
            })
            
    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
        
    return latest_posts

def check_new_notices():
    """새로운 글이 있는지 확인하고 구독자들에게 알림을 보냅니다."""
    if not TELEGRAM_TOKEN:
        print("오류: 환경변수에 TELEGRAM_TOKEN이 설정되지 않았습니다.")
        sys.exit(1)

    # 1. 구독자 목록 업데이트
    chat_ids = update_subscribers()
    if not chat_ids:
        print("등록된 구독자가 없습니다. 알림을 보낼 대상이 없습니다.")
        # 구독자가 없더라도 글 번호는 갱신해야 하므로 return 하지 않고 계속 진행합니다.

    # 2. 마지막 글 번호 불러오기
    last_num = 0
    if os.path.exists(LAST_NUM_FILE):
        with open(LAST_NUM_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content.isdigit():
                last_num = int(content)

    posts = get_latest_notices()
    if not posts:
        print("게시글을 불러오지 못했습니다.")
        return

    posts.reverse()
    new_last_num = last_num

    # 3. 새로운 글 확인 및 메시지 전송
    for post in posts:
        if last_num == 0:
            new_last_num = max(new_last_num, post['number'])
            continue

        if post['number'] > last_num:
            message = f"📢 <b>새로운 공지사항이 등록되었습니다!</b>\n\n"
            message += f"▪️ <b>제목:</b> {post['title']}\n"
            message += f"▪️ <b>링크:</b> <a href='{post['link']}'>바로가기</a>"
            
            if chat_ids:
                send_telegram_message(message, chat_ids)
                print(f"알림 전송 완료: {post['number']}번 글 (총 {len(chat_ids)}명)")
            
            new_last_num = max(new_last_num, post['number'])

    # 4. 마지막 글 번호 갱신
    if new_last_num > last_num or last_num == 0:
        with open(LAST_NUM_FILE, 'w', encoding='utf-8') as f:
            f.write(str(new_last_num))
        print(f"마지막 글 번호 업데이트 완료: {new_last_num}")
    else:
        print(f"새로운 공지사항이 없습니다. (현재 마지막 확인 글 번호: {last_num})")

if __name__ == "__main__":
    print("공지사항 크롤링 및 구독자 알림을 시작합니다...")
    check_new_notices()