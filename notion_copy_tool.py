import streamlit as st
from notion_client import Client
import json
from datetime import datetime
import pickle
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

# ページ設定
st.set_page_config(
    page_title="Notion一括コピーツール",
    page_icon="📝",
    layout="wide"
)

# キャッシュディレクトリ
CACHE_DIR = ".notion_cache"
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# セッション状態の初期化
if 'pages_data' not in st.session_state:
    st.session_state.pages_data = []
if 'selected_pages' not in st.session_state:
    st.session_state.selected_pages = set()
if 'filter_options' not in st.session_state:
    st.session_state.filter_options = {'categories': [], 'db_tags': []}
if 'select_all_checkbox' not in st.session_state:
    st.session_state.select_all_checkbox = False
if 'notion_token' not in st.session_state:
    st.session_state.notion_token = ""
if 'database_id' not in st.session_state:
    st.session_state.database_id = ""

def save_config(token, db_id):
    """設定を保存"""
    config = {
        'notion_token': token,
        'database_id': db_id
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def load_config():
    """設定を読み込み"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            return config.get('notion_token', ''), config.get('database_id', '')
        except:
            return '', ''
    return '', ''

# 起動時に設定を読み込み
if st.session_state.notion_token == "" and st.session_state.database_id == "":
    loaded_token, loaded_db_id = load_config()
    st.session_state.notion_token = loaded_token
    st.session_state.database_id = loaded_db_id

def init_page_checkboxes():
    """ページチェックボックスを初期化"""
    for page in st.session_state.pages_data:
        checkbox_key = f'page_check_{page["id"]}'
        if checkbox_key not in st.session_state:
            # 初期値を明示的に設定
            st.session_state[checkbox_key] = False

def changed_page_checkboxes_by_select_all():
    """全て選択をTrueにした場合、選択ボタンをすべてTrueにする"""
    if st.session_state.select_all_checkbox:
        for page in st.session_state.pages_data:
            checkbox_key = f'page_check_{page["id"]}'
            st.session_state[checkbox_key] = True
            st.session_state.selected_pages.add(page['id'])
    else:
        pass

def changed_select_all_by_page_checkboxes():
    """選択ボタンの状態に応じて全て選択を更新"""
    all_checked = True
    any_checked = False
    
    for page in st.session_state.pages_data:
        checkbox_key = f'page_check_{page["id"]}'
        if checkbox_key in st.session_state:
            if st.session_state[checkbox_key]:
                any_checked = True
                st.session_state.selected_pages.add(page['id'])
            else:
                all_checked = False
                st.session_state.selected_pages.discard(page['id'])
    
    if all_checked and len(st.session_state.pages_data) > 0:
        st.session_state.select_all_checkbox = True
    else:
        st.session_state.select_all_checkbox = False

def get_cache_path(database_id, filters):
    """キャッシュファイルのパスを生成"""
    filter_hash = hashlib.md5(str(filters).encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"cache_{database_id}_{filter_hash}.pkl")

def save_cache(database_id, filters, data):
    """キャッシュを保存"""
    cache_path = get_cache_path(database_id, filters)
    cache_data = {
        'timestamp': datetime.now(),
        'data': data
    }
    with open(cache_path, 'wb') as f:
        pickle.dump(cache_data, f)

def load_cache(database_id, filters):
    """キャッシュを読み込み"""
    cache_path = get_cache_path(database_id, filters)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)
            return cache_data
        except:
            return None
    return None

def extract_text_from_blocks(blocks):
    """ブロックからテキストを抽出"""
    text_content = []
    
    for block in blocks:
        block_type = block.get('type')
        
        if block_type == 'paragraph':
            rich_text = block.get('paragraph', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(text)
        
        elif block_type == 'heading_1':
            rich_text = block.get('heading_1', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"\n# {text}\n")
        
        elif block_type == 'heading_2':
            rich_text = block.get('heading_2', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"\n## {text}\n")
        
        elif block_type == 'heading_3':
            rich_text = block.get('heading_3', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"\n### {text}\n")
        
        elif block_type == 'bulleted_list_item':
            rich_text = block.get('bulleted_list_item', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"• {text}")
        
        elif block_type == 'numbered_list_item':
            rich_text = block.get('numbered_list_item', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"1. {text}")
        
        elif block_type == 'code':
            rich_text = block.get('code', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            language = block.get('code', {}).get('language', '')
            if text:
                text_content.append(f"```{language}\n{text}\n```")
        
        elif block_type == 'quote':
            rich_text = block.get('quote', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"> {text}")
        
        elif block_type == 'toggle':
            rich_text = block.get('toggle', {}).get('rich_text', [])
            text = ''.join([t.get('plain_text', '') for t in rich_text])
            if text:
                text_content.append(f"▸ {text}")
    
    return '\n'.join(text_content)

def get_page_content(notion, page_id):
    """ページの内容を取得"""
    try:
        page = notion.pages.retrieve(page_id=page_id)
        
        title = "無題"
        if 'properties' in page:
            for prop_name, prop_value in page['properties'].items():
                if prop_value.get('type') == 'title':
                    title_list = prop_value.get('title', [])
                    if title_list:
                        title = ''.join([t.get('plain_text', '') for t in title_list])
                    break
        
        blocks = []
        has_more = True
        start_cursor = None
        
        while has_more:
            if start_cursor:
                response = notion.blocks.children.list(
                    block_id=page_id,
                    start_cursor=start_cursor
                )
            else:
                response = notion.blocks.children.list(block_id=page_id)
            
            blocks.extend(response.get('results', []))
            has_more = response.get('has_more', False)
            start_cursor = response.get('next_cursor')
        
        content = extract_text_from_blocks(blocks)
        
        return {
            'id': page_id,
            'title': title,
            'content': content,
            'char_count': len(content),
            'line_count': len(content.split('\n'))
        }
    
    except Exception as e:
        return None

def get_filter_options(notion, database_id):
    """データベースからフィルタオプションを取得"""
    try:
        database = notion.databases.retrieve(database_id=database_id)
        properties = database.get('properties', {})
        
        options = {'categories': [], 'db_tags': []}
        
        if 'カテゴリ' in properties:
            prop = properties['カテゴリ']
            if prop.get('type') == 'select':
                select_options = prop.get('select', {}).get('options', [])
                options['categories'] = [opt.get('name') for opt in select_options]
            elif prop.get('type') == 'multi_select':
                select_options = prop.get('multi_select', {}).get('options', [])
                options['categories'] = [opt.get('name') for opt in select_options]
        
        if 'DB_tag' in properties:
            prop = properties['DB_tag']
            prop_type = prop.get('type')
            
            if prop_type == 'select':
                select_options = prop.get('select', {}).get('options', [])
                options['db_tags'] = [opt.get('name') for opt in select_options]
            elif prop_type == 'multi_select':
                select_options = prop.get('multi_select', {}).get('options', [])
                options['db_tags'] = [opt.get('name') for opt in select_options]
            elif prop_type == 'relation':
                relation_db_id = prop.get('relation', {}).get('database_id')
                if relation_db_id:
                    relation_pages = []
                    has_more = True
                    start_cursor = None
                    
                    while has_more:
                        if start_cursor:
                            response = notion.databases.query(
                                database_id=relation_db_id,
                                start_cursor=start_cursor
                            )
                        else:
                            response = notion.databases.query(database_id=relation_db_id)
                        
                        for page in response.get('results', []):
                            page_props = page.get('properties', {})
                            for prop_name, prop_value in page_props.items():
                                if prop_value.get('type') == 'title':
                                    title_list = prop_value.get('title', [])
                                    if title_list:
                                        title = ''.join([t.get('plain_text', '') for t in title_list])
                                        if title:
                                            relation_pages.append(title)
                                    break
                        
                        has_more = response.get('has_more', False)
                        start_cursor = response.get('next_cursor')
                    
                    options['db_tags'] = sorted(list(set(relation_pages)))
        
        return options
    except Exception as e:
        st.error(f"フィルタオプション取得エラー: {str(e)}")
        return {'categories': [], 'db_tags': []}

def build_filter_query(selected_categories, selected_db_tags):
    """Notion APIフィルタクエリを構築"""
    filters = []
    
    if selected_categories:
        if len(selected_categories) == 1:
            filters.append({
                "property": "カテゴリ",
                "select": {"equals": selected_categories[0]}
            })
        else:
            category_filters = [
                {"property": "カテゴリ", "select": {"equals": cat}}
                for cat in selected_categories
            ]
            filters.append({"or": category_filters})
    
    if selected_db_tags:
        if len(selected_db_tags) == 1:
            filters.append({
                "property": "DB_tag",
                "relation": {"contains": selected_db_tags[0]}
            })
        else:
            tag_filters = [
                {"property": "DB_tag", "relation": {"contains": tag}}
                for tag in selected_db_tags
            ]
            filters.append({"or": tag_filters})
    
    if len(filters) == 0:
        return None
    elif len(filters) == 1:
        return filters[0]
    else:
        return {"and": filters}

def load_database_pages(notion, database_id, filter_query=None, use_cache=True):
    """データベースから全ページを並列取得"""
    try:
        if use_cache:
            cached = load_cache(database_id, filter_query)
            if cached:
                cache_time = cached['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
                st.info(f"📦 キャッシュを使用 (取得日時: {cache_time})")
                return cached['data']
        
        page_ids = []
        has_more = True
        start_cursor = None
        
        with st.spinner('ページ一覧を取得中...'):
            while has_more:
                query_params = {"database_id": database_id}
                
                if filter_query:
                    query_params["filter"] = filter_query
                
                if start_cursor:
                    query_params["start_cursor"] = start_cursor
                
                response = notion.databases.query(**query_params)
                
                for page in response.get('results', []):
                    page_ids.append(page['id'])
                
                has_more = response.get('has_more', False)
                start_cursor = response.get('next_cursor')
        
        if len(page_ids) == 0:
            st.warning("⚠️ フィルタ条件に一致するページが見つかりませんでした")
            return []
        
        pages_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_id = {
                executor.submit(get_page_content, notion, page_id): page_id 
                for page_id in page_ids
            }
            
            completed = 0
            total = len(page_ids)
            
            for future in as_completed(future_to_id):
                page_content = future.result()
                if page_content:
                    pages_data.append(page_content)
                
                completed += 1
                progress_bar.progress(completed / total)
                status_text.text(f"読み込み中: {completed}/{total} ページ")
        
        progress_bar.empty()
        status_text.empty()
        
        save_cache(database_id, filter_query, pages_data)
        
        return pages_data
    
    except Exception as e:
        st.error(f"データベース読み込みエラー: {str(e)}")
        return []

# メインUI
st.title("📝 Notion一括コピーツール")
st.markdown("---")

# サイドバー: 設定
with st.sidebar:
    st.header("⚙️ 設定")
    
    notion_token = st.text_input(
        "Notion API Token",
        value=st.session_state.notion_token,
        type="password",
        help="Notionインテグレーションのトークンを入力"
    )
    
    database_id = st.text_input(
        "データベースID",
        value=st.session_state.database_id,
        help="NotionデータベースのIDを入力"
    )
    
    if notion_token != st.session_state.notion_token or database_id != st.session_state.database_id:
        st.session_state.notion_token = notion_token
        st.session_state.database_id = database_id
        if notion_token and database_id:
            save_config(notion_token, database_id)
    
    if st.button("🔍 フィルタ設定を読み込み", use_container_width=True):
        if not notion_token or not database_id:
            st.error("API TokenとデータベースIDを入力してください")
        else:
            try:
                with st.spinner('フィルタ設定を読み込み中...'):
                    notion = Client(auth=notion_token)
                    st.session_state.filter_options = get_filter_options(notion, database_id)
                st.success("✅ フィルタ設定を読み込みました!")
            except Exception as e:
                st.error(f"❌ エラー: {str(e)}")
    
    st.markdown("---")
    st.subheader("📋 フィルタ条件")
    
    selected_categories = []
    if st.session_state.filter_options['categories']:
        # すべて選択ボタン（カテゴリ）
        if st.button("✅ カテゴリ: すべて選択", use_container_width=True, key="select_all_categories"):
            # セッション状態に保存して、プルダウンのデフォルト値として使用
            st.session_state['selected_categories_default'] = st.session_state.filter_options['categories']
            st.rerun()
        
        # デフォルト値の設定
        default_categories = st.session_state.get('selected_categories_default', [])
        
        selected_categories = st.multiselect(
            "カテゴリ",
            options=st.session_state.filter_options['categories'],
            default=default_categories,
            help="複数選択可能(OR条件)"
        )
        
        # 選択が変更されたらデフォルト値をクリア
        if selected_categories != default_categories:
            st.session_state['selected_categories_default'] = selected_categories
    else:
        st.caption("フィルタ設定を読み込んでください")
    
    selected_db_tags = []
    if st.session_state.filter_options['db_tags']:
        # すべて選択ボタン（DB_tag）
        if st.button("✅ DB_tag: すべて選択", use_container_width=True, key="select_all_db_tags"):
            # セッション状態に保存して、プルダウンのデフォルト値として使用
            st.session_state['selected_db_tags_default'] = st.session_state.filter_options['db_tags']
            st.rerun()
        
        # デフォルト値の設定
        default_db_tags = st.session_state.get('selected_db_tags_default', [])
        
        selected_db_tags = st.multiselect(
            "DB_tag",
            options=st.session_state.filter_options['db_tags'],
            default=default_db_tags,
            help="複数選択可能(OR条件)"
        )
        
        # 選択が変更されたらデフォルト値を更新
        if selected_db_tags != default_db_tags:
            st.session_state['selected_db_tags_default'] = selected_db_tags
    
    st.markdown("---")
    
    use_cache = st.checkbox("キャッシュを使用", value=True, help="前回の読み込み結果を再利用")
    
    if st.button("🔄 ページを読み込み", use_container_width=True, type="primary"):
        if not notion_token or not database_id:
            st.error("API TokenとデータベースIDを入力してください")
        else:
            try:
                notion = Client(auth=notion_token)
                filter_query = build_filter_query(selected_categories, selected_db_tags)
                st.session_state.pages_data = load_database_pages(
                    notion, 
                    database_id, 
                    filter_query,
                    use_cache
                )
                st.session_state.selected_pages = set()
                st.success(f"✅ {len(st.session_state.pages_data)}件のページを読み込みました!")
            except Exception as e:
                st.error(f"エラー: {str(e)}")
    
    if st.button("🗑️ キャッシュをクリア", use_container_width=True):
        import shutil
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            os.makedirs(CACHE_DIR)
            st.success("キャッシュをクリアしました!")
    
    st.markdown("---")
    st.markdown(f"**読み込み済み:** {len(st.session_state.pages_data)}件")
    st.markdown(f"**選択中:** {len(st.session_state.selected_pages)}件")

# メインエリア
if len(st.session_state.pages_data) == 0:
    st.info("👈 サイドバーからフィルタ設定を読み込み、ページを取得してください")
    
    with st.expander("📖 使い方ガイド"):
        st.markdown("""
        ### ステップ1: 初期設定
        1. Notion API Tokenを入力
        2. データベースIDを入力
        3. 「フィルタ設定を読み込み」をクリック
        
        ### ステップ2: フィルタ条件を設定
        1. カテゴリやDB_tagから絞り込み条件を選択
        2. 「ページを読み込み」をクリック
        
        ### ステップ3: ページを選択してコピー
        1. 検索ボックスでさらに絞り込み
        2. 必要なページにチェック
        3. 「テキストを表示」または「テキストファイルとして保存」
        
        ### 💡 Tips
        - **キャッシュ機能**: 一度読み込んだデータは保存され、次回は高速に表示されます
        - **並列処理**: 複数ページを同時に取得するため、大量のページも素早く読み込めます
        - **フィルタ**: 必要なページだけを取得することで、読み込み時間を大幅に短縮できます
        """)
else:
    col1, col2 = st.columns([7, 1])
    with col1:
        search_query = st.text_input(
            "🔍 検索",
            placeholder="ページタイトルまたは本文で検索...",
            label_visibility="collapsed",
            key="search_box"
        )
    with col2:
        search_button = st.button("🔍 検索", use_container_width=True)
    
    filtered_pages = st.session_state.pages_data
    if search_query:
        filtered_pages = [
            p for p in st.session_state.pages_data
            if search_query.lower() in p['title'].lower() or 
               search_query.lower() in p['content'].lower()
        ]
    
    init_page_checkboxes()
    
    col1, col2 = st.columns([1, 5])
    with col1:
        st.checkbox(
            "✅ すべて選択",
            value=st.session_state.select_all_checkbox,
            key='select_all_checkbox',
            on_change=changed_page_checkboxes_by_select_all
        )
    with col2:
        st.markdown(f"**表示中:** {len(filtered_pages)}件 / 全{len(st.session_state.pages_data)}件")
    
    st.markdown("---")
    
    for idx, page in enumerate(filtered_pages):
        col1, col2, col3 = st.columns([0.5, 6, 2])
        
        with col1:
            checkbox_key = f'page_check_{page["id"]}'
            
            st.checkbox(
                label=f"選択_{page['id']}",
                key=checkbox_key,
                label_visibility="collapsed",
                on_change=changed_select_all_by_page_checkboxes
            )
        
        with col2:
            st.markdown(f"**{page['title']}**")
            preview = page['content'][:100].replace('\n', ' ')
            st.caption(f"{preview}..." if len(page['content']) > 100 else preview)
        
        with col3:
            st.caption(f"📄 {page['line_count']}行 / {page['char_count']}文字")
    
    st.markdown("---")
    col1, col2 = st.columns([2, 2])
    
    with col1:
        if st.button("📄 テキストを表示", use_container_width=True, type="primary"):
            if len(st.session_state.selected_pages) == 0:
                st.warning("ページを選択してください")
            else:
                selected_content = []
                for page in st.session_state.pages_data:
                    if page['id'] in st.session_state.selected_pages:
                        selected_content.append(f"# {page['title']}\n\n{page['content']}")
                
                combined_text = "\n\n" + "="*80 + "\n\n".join(selected_content)
                
                st.text_area(
                    "以下のテキストを選択してコピーしてください (Ctrl+A → Ctrl+C)",
                    combined_text,
                    height=300,
                    key="copy_area"
                )
                st.info("💡 テキストエリア内をクリック → Ctrl+A(全選択) → Ctrl+C(コピー)")
    
    with col2:
        if st.button("💾 テキストファイルとして保存", use_container_width=True):
            if len(st.session_state.selected_pages) == 0:
                st.warning("ページを選択してください")
            else:
                selected_content = []
                for page in st.session_state.pages_data:
                    if page['id'] in st.session_state.selected_pages:
                        selected_content.append(f"# {page['title']}\n\n{page['content']}")
                
                combined_text = "\n\n" + "="*80 + "\n\n".join(selected_content)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                st.download_button(
                    label="⬇️ ダウンロード",
                    data=combined_text,
                    file_name=f"notion_pages_{timestamp}.txt",
                    mime="text/plain"
                )