#!/usr/bin/env python3
"""
补充下载 OWASP CheatSheet 安全文档

来源: OWASP CheatSheetSeries (github.com/OWASP/CheatSheetSeries)
权威安全指南，覆盖 Web 应用安全的各个维度。
"""

import time
from pathlib import Path

import requests

KB_DIR = Path("D:/PythonProjects/OSScout/knowledge-base")
OUT_DIR = KB_DIR / "security" / "owasp"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHEATSHEETS = [
    "Abuse_Case_Cheat_Sheet.md",
    "Access_Control_Cheat_Sheet.md",
    "Authentication_Cheat_Sheet.md",
    "Authorization_Cheat_Sheet.md",
    "Business_Logic_Security_Cheat_Sheet.md",
    "CI_CD_Security_Cheat_Sheet.md",
    "Clickjacking_Defense_Cheat_Sheet.md",
    "Content_Security_Policy_Cheat_Sheet.md",
    "Credential_Stuffing_Prevention_Cheat_Sheet.md",
    "Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md",
    "Cross_Site_Scripting_Prevention_Cheat_Sheet.md",
    "Cryptographic_Storage_Cheat_Sheet.md",
    "Deserialization_Cheat_Sheet.md",
    "DOM_based_XSS_Prevention_Cheat_Sheet.md",
    "Error_Handling_Cheat_Sheet.md",
    "File_Upload_Cheat_Sheet.md",
    "Forgot_Password_Cheat_Sheet.md",
    "HTML5_Security_Cheat_Sheet.md",
    "HTTP_Strict_Transport_Security_Cheat_Sheet.md",
    "Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.md",
    "Injection_Prevention_Cheat_Sheet.md",
    "JSON_Web_Token_for_Java_Cheat_Sheet.md",
    "Key_Management_Cheat_Sheet.md",
    "LDAP_Injection_Prevention_Cheat_Sheet.md",
    "Logging_Cheat_Sheet.md",
    "Mass_Assignment_Cheat_Sheet.md",
    "Multifactor_Authentication_Cheat_Sheet.md",
    "Nodejs_Security_Cheat_Sheet.md",
    "OS_Command_Injection_Defense_Cheat_Sheet.md",
    "Password_Storage_Cheat_Sheet.md",
    "Pinning_Cheat_Sheet.md",
    "Query_Parameterization_Cheat_Sheet.md",
    "REST_Security_Cheat_Sheet.md",
    "Ruby_on_Rails_Cheat_Sheet.md",
    "SAML_Security_Cheat_Sheet.md",
    "SQL_Injection_Prevention_Cheat_Sheet.md",
    "Secrets_Management_Cheat_Sheet.md",
    "Session_Management_Cheat_Sheet.md",
    "Threat_Modeling_Cheat_Sheet.md",
    "TLS_Cheat_Sheet.md",
    "Transaction_Authorization_Cheat_Sheet.md",
    "Transport_Layer_Protection_Cheat_Sheet.md",
    "Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md",
    "User_Privacy_Protection_Cheat_Sheet.md",
    "Vulnerability_Disclosure_Cheat_Sheet.md",
    "Web_Service_Security_Cheat_Sheet.md",
    "XML_External_Entity_Prevention_Cheat_Sheet.md",
    "XML_Security_Cheat_Sheet.md",
]

BASE_URL = "https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/"


def download(filename: str) -> bool:
    """下载单个 CheatSheet"""
    url = BASE_URL + filename
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  FAIL({resp.status_code}): {filename}")
            return False

        # 添加 frontmatter
        title = filename.replace("_Cheat_Sheet.md", "").replace("_", " ")
        frontmatter = f"""---
title: OWASP: {title}
source: https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/{filename}
category: security/owasp
downloaded_at: 2026-05-21
---

"""
        out_path = OUT_DIR / filename.lower().replace("_cheat_sheet.md", ".md")
        out_path.write_text(frontmatter + resp.text, encoding="utf-8")
        print(f"  OK: {filename} -> {out_path.name}")
        return True
    except Exception as e:
        print(f"  ERR: {filename} - {e}")
        return False


def main():
    print("=" * 60)
    print("下载 OWASP CheatSheet 安全文档")
    print(f"输出目录: {OUT_DIR}")
    print("=" * 60)

    success = 0
    for filename in CHEATSHEETS:
        if download(filename):
            success += 1
        time.sleep(0.5)  # 礼貌间隔

    print(f"\n完成: {success}/{len(CHEATSHEETS)} 篇")


if __name__ == "__main__":
    main()
