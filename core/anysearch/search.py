import requests
import json

# 1. 定义请求的URL
url = "https://api.anysearch.com/v1/search"

# 2. 设置请求头 (Headers)
# 注意：请将 'YOUR_ANYSEARCH_API_KEY' 替换为你实际的 API 密钥
headers = {
    "Authorization": "Bearer as_sk_faa3f6ebdcfd8d3bd24bea12ed439fd4",
    "Content-Type": "application/json"
}

# 3. 准备请求体 (Payload/Data)
# 这里包含了你的查询语句、最大返回结果数以及过滤的域名和内容类型
data = {
    "query": "蓝海赛道",
    "max_results": 5,
    "domains":  ["business", "tech", "general"] ,
    "content_types": ["web", "doc"],
    "raw_content": True  # 尝试加入此参数
}

# 4. 发送 POST 请求
# 使用 json=data 参数会自动将字典转换为 JSON 字符串并设置正确的 Content-Type
response = requests.post(url, json=data, headers=headers)

# 5. 处理响应
if response.status_code == 200:
    # 如果请求成功，打印返回的 JSON 数据
    print("请求成功！返回结果：")
    print(response.json())
    # 将 response.json() 获取的字典对象，通过 json.dumps 美化后打印
    print(json.dumps(response.json(), indent=4, ensure_ascii=False))
else:
    # 如果请求失败，打印错误状态码和原因
    print(f"请求失败，状态码：{response.status_code}")
    print(response.text)