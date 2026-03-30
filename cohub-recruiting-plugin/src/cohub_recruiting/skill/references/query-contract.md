# Query Contract

The recruiting assistant normalizes natural-language search requests into a shared query object before invoking site MCP adapters.

```json
{
  "sites": [],
  "keyword": "",
  "position": "",
  "company": "",
  "current_city": "",
  "expected_city": "",
  "experience": "",
  "education": "",
  "current_industry": "",
  "expected_industry": "",
  "current_function": "",
  "expected_function": "",
  "current_salary": "",
  "expected_salary": "",
  "school": "",
  "major": "",
  "active_status": "",
  "job_status": "",
  "management_experience": "",
  "page": 1,
  "page_size_limit": 20
}
```

Rules:

- only populate fields clearly implied by the user
- default to all enabled recruiting sites unless the user narrows the scope
- treat follow-up turns as incremental refinement unless the user explicitly resets the search
- preserve the previous successful title scope on follow-up turns unless the user explicitly replaces it
- do not silently broaden titles like `HR产品经理` into `产品经理`
- map `现在在青岛` to `current_city="青岛"`
- map `能来青岛` or `期望青岛` to `expected_city="青岛"`
- map `能来青岛或者现在在青岛都行` to both `expected_city="青岛"` and `current_city="青岛"`
