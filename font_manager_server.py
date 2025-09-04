import os
import sys
import json
import re
import uvicorn
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, status, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pathlib import Path
from typing import List, Dict
from contextlib import asynccontextmanager

# --- 基础配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 全局变量 ---
CONFIG: Dict[str, any] = {}
SILLY_TAVERN_PATH: Path | None = None

# --- Pydantic 模型 ---
class FontDeletePayload(BaseModel):
    fontFamily: str
    fileName: str
class FontEditPayload(BaseModel):
    oldFontFamily: str
    newFontFamily: str
    fileName: str

# --- 辅助函数 ---
def load_dependencies():
    """【【【V4.0 新增】】】加载所有外部依赖项，如配置和路径。"""
    global CONFIG, SILLY_TAVERN_PATH
    # 1. 加载 config.jsonc
    try:
        with open("config.jsonc", 'r', encoding='utf-8') as f:
            content = f.read()
            json_content = re.sub(r'//.*|/\*[\s\S]*?\*/', '', content)
            CONFIG = json.loads(json_content)
        logger.info("✅ config.jsonc 文件加载成功。")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"⚠️ 未能加载或解析 config.jsonc: {e}。将依赖环境变量。")
        CONFIG = {}

    # 2. 决定 SillyTavern 路径
    #    优先从环境变量 SILLY_TAVERN_PATH 获取
    path_str = os.environ.get("SILLY_TAVERN_PATH")
    if path_str:
        logger.info(f"✅ 从环境变量中获取 SillyTavern 路径: {path_str}")
    else:
        # 如果环境变量没有，则回退到从 config.jsonc 获取
        path_str = CONFIG.get("sillytavern_path")
        if path_str:
            logger.info(f"✅ 从配置文件中获取 SillyTavern 路径: {path_str}")

    if not path_str:
        logger.error("❌ 致命错误: 必须通过环境变量 'SILLY_TAVERN_PATH' 或在 config.jsonc 中提供 'sillytavern_path'！")
        sys.exit(1)
        
    SILLY_TAVERN_PATH = Path(path_str)
    if not SILLY_TAVERN_PATH.exists() or not SILLY_TAVERN_PATH.is_dir():
        logger.warning(f"⚠️ 警告: 配置的 SillyTavern 路径 '{SILLY_TAVERN_PATH}' 不存在或不是一个目录。程序可能会在文件操作时失败。")


def get_sillytavern_paths():
    """【【【V4.0 修改】】】直接使用已加载的全局路径。"""
    if not SILLY_TAVERN_PATH:
        # 这是一个安全检查，理论上不应该发生
        raise HTTPException(status_code=500, detail="SillyTavern path not configured.")
    public_path = SILLY_TAVERN_PATH / "public"
    font_dir = public_path / "webfonts" / "myfonts"
    css_file = public_path / "css" / "user.css"
    return font_dir, css_file

# --- FastAPI 生命周期事件 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dependencies()
    yield
    logger.info("服务器正在关闭。")

# --- FastAPI 应用实例 ---
app = FastAPI(lifespan=lifespan)
# ... 此处省略其他未改变的Python代码 (API端点、HTML页面等) ...
# 为了简洁，这里省略了所有API端点和前端页面的Python代码，因为它们都没有改变。
# 您只需替换整个 .py 文件即可。
security = HTTPBearer()
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    server_api_key = CONFIG.get("api_key");
    if not server_api_key: return "admin"
    if credentials and credentials.credentials == server_api_key: return "admin"
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect API Key")
def get_font_face_blocks(content: str) -> List[str]:
    return re.findall(r"@font-face\s*\{[^\}]*\}", content, re.DOTALL | re.IGNORECASE)
def parse_user_css():
    _, css_file = get_sillytavern_paths();
    if not css_file.exists(): return []
    with open(css_file, 'r', encoding='utf-8') as f: content = f.read()
    fonts = []
    for block in get_font_face_blocks(content):
        family_match = re.search(r"font-family:\s*['\"]([^'\"]+)['\"]", block, re.IGNORECASE)
        src_match = re.search(r"src:\s*url\(['\"]([^'\"]+)['\"]\)", block, re.IGNORECASE)
        if family_match and src_match:
            font_family = family_match.group(1); src_path = src_match.group(1); file_name = os.path.basename(src_path)
            fonts.append({"fontFamily": font_family, "fileName": file_name})
    return fonts
def update_css_file(new_content: str):
    _, css_file = get_sillytavern_paths()
    try:
        with open(css_file, 'w', encoding='utf-8') as f: f.write(new_content.strip() + "\n")
        logger.info("✅ user.css 文件已成功更新。"); return True
    except Exception as e: logger.error(f"❌ 写入 user.css 文件失败: {e}"); raise HTTPException(status_code=500, detail="Failed to write to user.css file.")
def add_font_to_css(font_family: str, font_weight: str, font_style: str, file_name: str):
    _, css_file = get_sillytavern_paths(); font_url = f"/webfonts/myfonts/{file_name}"
    new_rule = f"\n/* --- Added by Font Manager Panel --- */\n@font-face {{\n  font-family: '{font_family}';\n  src: url('{font_url}');\n  font-weight: {font_weight};\n  font-style: {font_style};\n}}\n"
    try:
        with open(css_file, 'a', encoding='utf-8') as f: f.write(new_rule)
        logger.info(f"成功将字体 '{font_family}' 的规则追加到 user.css。")
    except Exception as e: logger.error(f"写入 user.css 文件失败: {e}"); raise HTTPException(status_code=500, detail="Failed to write to user.css file.")
@app.get("/api/list-fonts", response_model=list)
async def list_fonts(current_user: str = Depends(get_current_user)):
    try: return parse_user_css()
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/upload-font")
async def upload_font(font_file: UploadFile = File(...), font_family: str = Form(...), font_weight: str = Form(...), font_style: str = Form(...), current_user: str = Depends(get_current_user)):
    font_dir, _ = get_sillytavern_paths(); os.makedirs(font_dir, exist_ok=True)
    file_path = font_dir / font_file.filename
    if file_path.exists(): raise HTTPException(status_code=409, detail=f"File '{font_file.filename}' already exists.")
    try:
        with open(file_path, "wb") as buffer: buffer.write(await font_file.read())
        logger.info(f"字体文件 '{font_file.filename}' 已保存。")
    except Exception as e: logger.error(f"保存文件失败: {e}"); raise HTTPException(status_code=500, detail="Failed to save file.")
    add_font_to_css(font_family, font_weight, font_style, font_file.filename)
    return {"status": "success", "message": "Font uploaded."}
@app.post("/api/delete-font")
async def delete_font(payload: FontDeletePayload, current_user: str = Depends(get_current_user)):
    font_dir, css_file = get_sillytavern_paths(); font_file_path = font_dir / payload.fileName
    if css_file.exists():
        with open(css_file, 'r', encoding='utf-8') as f: content = f.read()
        all_blocks = get_font_face_blocks(content); blocks_to_keep = []
        for block in all_blocks:
            if not ((f"'{payload.fontFamily}'" in block or f'"{payload.fontFamily}"' in block) and (f"/{payload.fileName}" in block)): blocks_to_keep.append(block)
        other_css_rules = content
        for block in all_blocks: other_css_rules = other_css_rules.replace(block, '')
        final_content = (other_css_rules.strip() + "\n\n" + "\n".join(blocks_to_keep)).strip()
        update_css_file(final_content)
    if font_file_path.exists():
        try: os.remove(font_file_path); logger.info(f"成功删除字体文件: {payload.fileName}")
        except Exception as e: logger.error(f"删除字体文件失败: {e}"); raise HTTPException(status_code=500, detail="Failed to delete font file.")
    return {"status": "success", "message": "Font deleted."}
@app.post("/api/edit-font")
async def edit_font(payload: FontEditPayload, current_user: str = Depends(get_current_user)):
    _, css_file = get_sillytavern_paths();
    if not css_file.exists(): raise HTTPException(status_code=404, detail="user.css not found.")
    with open(css_file, 'r', encoding='utf-8') as f: content = f.read()
    all_blocks = get_font_face_blocks(content); new_blocks = []; edited_count = 0
    for block in all_blocks:
        if (f"'{payload.oldFontFamily}'" in block or f'"{payload.oldFontFamily}"' in block) and (f"/{payload.fileName}" in block):
            new_block = re.sub(r"(font-family\s*:\s*['\"])([^'\"]+)(['\"])", rf"\g<1>{payload.newFontFamily}\g<3>", block, count=1, flags=re.IGNORECASE)
            new_blocks.append(new_block); edited_count += 1
        else: new_blocks.append(block)
    if edited_count > 0:
        other_css_rules = content
        for block in all_blocks: other_css_rules = other_css_rules.replace(block, '')
        final_content = (other_css_rules.strip() + "\n\n" + "\n".join(new_blocks)).strip()
        update_css_file(final_content)
        return {"status": "success", "message": "Font alias updated."}
    else: raise HTTPException(status_code=404, detail="Matching font rule not found to edit.")
@app.get("/", response_class=HTMLResponse)
async def get_login_page():
    return HTMLResponse(content="""
    <!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>字体管理面板 - 登录</title>
    <style>body{display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background-color:#1a1a1a;color:#f0f0f0;font-family:sans-serif}.auth-box{background:#2a2a2a;padding:2em 3em;border-radius:8px;box-shadow:0 5px 20px rgba(0,0,0,0.7);text-align:center}h2{color:#8ab4f8}input{padding:10px;margin:15px 0;width:280px;background:#3c3c3c;border:1px solid #555;border-radius:4px;color:#fff}button{width:100%;padding:10px 20px;background:#8ab4f8;color:#1a1a1a;border:none;border-radius:4px;font-weight:700;cursor:pointer}</style>
    </head><body><div class="auth-box"><h2>SillyTavern 字体管理面板</h2><p>请输入 API Key。</p><input type="password" id="api-key-input" placeholder="API Key"><button onclick="login()">进入</button></div>
    <script>
        function login(){const a=document.getElementById('api-key-input').value;a?(localStorage.setItem('fontManagerApiKey',a),window.location.href='/admin'):alert('请输入 API Key！')}
        document.getElementById('api-key-input').addEventListener('keyup',e=>{e.key==='Enter'&&login()});
    </script></body></html>
    """)
@app.get("/admin", response_class=HTMLResponse)
async def get_admin_page():
    # --- v5.2 - 根据用户建议，新增独立的字体预览面板 ---
    html_content = """
    <!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>字体管理面板</title>
    <style>
        body{font-family:sans-serif;background-color:#1a1a1a;color:#f0f0f0;margin:0;padding:2em}
        .container{max-width:900px;margin:auto}h1{color:#8ab4f8;text-align:center;margin-bottom:1.5em}
        .panel{background-color:#2a2a2a;border:1px solid #444;border-radius:8px;padding:1.5em;margin-bottom:2em}
        h2{margin-top:0;border-bottom:1px solid #555;padding-bottom:10px}
        .form-grid{display:grid;grid-template-columns:auto 1fr;gap:15px;align-items:center}
        label{font-weight:bold;text-align:right}
        input,select,button,textarea{padding:10px;background:#3c3c3c;border:1px solid #555;border-radius:4px;color:#f0f0f0;box-sizing:border-box; font-size: 1em;}
        .form-grid > button{background:#8ab4f8;color:#1a1a1a;font-weight:700;cursor:pointer;grid-column:1/-1}
        #font-list table{width:100%;border-collapse:collapse;margin-top:1em}
        #font-list th,#font-list td{padding:12px;text-align:left;border-bottom:1px solid #444;vertical-align:middle}
        #font-list th{background-color:#3c3c3c}
        .loading,.error{text-align:center;color:#888;padding:2em}
        .file-upload-wrapper{display:flex;align-items:center;gap:10px}
        .file-upload-button{background-color:#555;padding:10px 15px;border-radius:4px;cursor:pointer;white-space:nowrap}
        .file-name-display{color:#aaa;font-style:italic;font-size:0.9em}
        #font-file{display:none}
        .action-btn{border:none;padding:8px 12px;border-radius:6px;cursor:pointer;font-weight:bold;margin-right:8px}
        .edit-btn{background-color:#1976d2} .edit-btn:hover{background-color:#115293}
        .delete-btn{background-color:#da3633} .delete-btn:hover{background-color:#b92521}
        /* --- 新增预览区样式 --- */
        .preview-controls{display:flex;gap:15px;margin-bottom:15px}
        #font-preview-select{flex-basis:250px;}
        #font-preview-input{width:100%;min-height:100px;resize:vertical;font-size:24px;line-height:1.5;}
    </style>
    </head><body><div class="container"><h1>SillyTavern 字体管理面板</h1>
    <div class="panel"><h2>上传新字体</h2><form id="upload-form" class="form-grid">
        <label for="font-file-button">字体文件</label>
        <div class="file-upload-wrapper"><input type="file" id="font-file" name="font_file" accept=".ttf,.otf,.woff,.woff2" required><label for="font-file" id="font-file-button" class="file-upload-button">选择文件</label><span id="file-name-display">未选择任何文件</span></div>
        <label for="font-family">字体别名 (font-family)</label><input type="text" id="font-family" name="font_family" placeholder="例如: 像素字" required>
        <label for="font-weight">字体粗细 (font-weight)</label><select id="font-weight" name="font_weight" required><option value="400" selected>400 - Normal</option><option value="700">700 - Bold</option><option value="100">100 - Thin</option><option value="200">200 - Extra Light</option><option value="300">300 - Light</option><option value="500">500 - Medium</option><option value="600">600 - Semi Bold</option><option value="800">800 - Extra Bold</option><option value="900">900 - Black</option></select>
        <label for="font-style">字体样式 (font-style)</label><select id="font-style" name="font_style" required><option value="normal" selected>Normal</option><option value="italic">Italic</option><option value="oblique">Oblique</option></select>
        <button type="submit">上传并配置</button></form></div>
    
    <div class="panel"><h2>字体效果实时预览</h2>
        <div class="preview-controls">
            <select id="font-preview-select"><option value="">-- 请选择一个字体 --</option></select>
        </div>
        <textarea id="font-preview-input" placeholder="在这里输入文字来预览效果...">The quick brown fox jumps over the lazy dog. 1234567890</textarea>
    </div>

    <div class="panel"><h2>已安装字体列表</h2><div id="font-list"><p class="loading">正在加载...</p></div></div></div>
    <script>
    document.addEventListener('DOMContentLoaded',()=>{
        const apiKey=localStorage.getItem('fontManagerApiKey'); if(!apiKey){window.location.href='/';return}
        const fontListDiv=document.getElementById('font-list'); const uploadForm=document.getElementById('upload-form');
        const fileInput=document.getElementById('font-file'); const fileNameDisplay=document.getElementById('file-name-display');
        
        // --- 新增预览区元素引用 ---
        const fontPreviewSelect = document.getElementById('font-preview-select');
        const fontPreviewInput = document.getElementById('font-preview-input');

        fileInput.addEventListener('change',()=>{fileNameDisplay.textContent=fileInput.files.length>0?fileInput.files[0].name:'未选择任何文件'});
        
        async function loadFonts(){
            try{
                const response=await fetch('/api/list-fonts',{headers:{'Authorization':`Bearer ${apiKey}`}});
                if(response.status===401){alert('认证失败，请重新登录。');window.location.href='/';return}
                if(!response.ok)throw new Error('服务器错误: '+response.status);
                const fonts=await response.json();
                
                // --- 渲染字体列表 (已移除之前的内联预览样式) ---
                let tableHtml='<table><thead><tr><th>CSS 别名</th><th>文件名</th><th>操作</th></tr></thead><tbody>';
                if(fonts.length===0){tableHtml+='<tr><td colspan="3" style="text-align:center">当前没有已配置的字体。</td></tr>'}
                else{fonts.forEach(f=>{tableHtml+=`
                    <tr id="font-row-${f.fileName.replace(/[^a-zA-Z0-9]/g,'')}">
                        <td class="font-family-cell">${f.fontFamily}</td>
                        <td>${f.fileName}</td>
                        <td>
                          <button class="action-btn edit-btn" data-family="${f.fontFamily}" data-file="${f.fileName}">编辑</button>
                          <button class="action-btn delete-btn" data-family="${f.fontFamily}" data-file="${f.fileName}">删除</button>
                        </td>
                    </tr>`})}
                tableHtml+='</tbody></table>';
                fontListDiv.innerHTML=tableHtml;

                // --- 【【【新增】】】 动态填充预览下拉菜单 ---
                let selectHtml = '<option value="">-- 请选择一个字体 --</option>';
                fonts.forEach(f => {
                    selectHtml += `<option value="${f.fontFamily}">${f.fontFamily}</option>`;
                });
                fontPreviewSelect.innerHTML = selectHtml;

            }catch(e){fontListDiv.innerHTML=`<p class="error">加载失败: ${e.message}</p>`}
        }

        // --- 【【【新增】】】 更新预览效果的函数 ---
        function updatePreview() {
            const selectedFont = fontPreviewSelect.value;
            if (selectedFont) {
                fontPreviewInput.style.fontFamily = `'${selectedFont}', sans-serif`;
            } else {
                fontPreviewInput.style.fontFamily = ''; // 重置为默认字体
            }
        }

        // --- 【【【新增】】】 为预览控件添加事件监听 ---
        fontPreviewSelect.addEventListener('change', updatePreview);
        fontPreviewInput.addEventListener('input', updatePreview); // 输入时也触发，虽然字体不变，但保持逻辑一致性

        uploadForm.addEventListener('submit',async e=>{e.preventDefault();if(fileInput.files.length===0){alert('请先选择一个字体文件！');return}const formData=new FormData();formData.append('font_file',fileInput.files[0]);formData.append('font_family',document.getElementById('font-family').value);formData.append('font_weight',document.getElementById('font-weight').value);formData.append('font_style',document.getElementById('font-style').value);const button=uploadForm.querySelector('button');button.disabled=true;button.textContent='上传中...';try{const response=await fetch('/api/upload-font',{method:'POST',headers:{'Authorization':`Bearer ${apiKey}`},body:formData});const result=await response.json();if(!response.ok){throw new Error(result.detail||'上传失败')}alert('上传成功！');uploadForm.reset();fileNameDisplay.textContent='未选择任何文件';await loadFonts()}catch(e){alert(`上传失败: ${e.message}`)}finally{button.disabled=false;button.textContent='上传并配置'}});
        fontListDiv.addEventListener('click',async e=>{const btn=e.target;const fontFamily=btn.dataset.family;const fileName=btn.dataset.file;if(btn.classList.contains('delete-btn')){if(!confirm(`确定要删除字体'${fontFamily}'吗？\\n\\n此操作将删除文件并更新CSS，不可逆！`))return;try{const response=await fetch('/api/delete-font',{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${apiKey}`},body:JSON.stringify({fontFamily,fileName})});if(!response.ok){const err=await response.json();throw new Error(err.detail)}alert('删除成功！');await loadFonts();}catch(err){alert(`删除失败: ${err.message}`)}}
        if(btn.classList.contains('edit-btn')){const newFontFamily=prompt('请输入新的字体别名 (font-family):',fontFamily);if(newFontFamily&&newFontFamily.trim()!==''&&newFontFamily!==fontFamily){try{const response=await fetch('/api/edit-font',{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${apiKey}`},body:JSON.stringify({oldFontFamily:fontFamily,newFontFamily,fileName})});if(!response.ok){const err=await response.json();throw new Error(err.detail)}alert('编辑成功！请记得去SillyTavern中更新对应的正则美化规则。');await loadFonts();}catch(err){alert(`编辑失败: ${err.message}`)}}}});
        
        loadFonts();
    });
    </script></body></html>
    """
    return HTMLResponse(content=html_content)
# --- 主程序入口 ---
if __name__ == "__main__":
    default_port = int(os.environ.get("PORT", 7860))
    logger.info(f"🚀 SillyTavern 字体管理面板 v5.0 正在启动...")
    logger.info(f"   - 容器内部监听端口: {default_port}")
    uvicorn.run(app, host="0.0.0.0", port=default_port)


