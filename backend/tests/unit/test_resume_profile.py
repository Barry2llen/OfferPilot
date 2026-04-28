import pytest
from pydantic import ValidationError

from schemas.resume_profile import ResumeProfile


def _build_profile_payload() -> dict:
    return {
        "basic_info": {
            "full_name": "张三",
            "headline": "高级后端开发工程师",
            "phone": "13800000000",
            "email": "zhangsan@example.com",
            "current_city": "上海",
        },
        "educations": [
            {
                "school_name": "浙江大学",
                "major": "软件工程",
                "education_level": "本科",
                "start_date": "2015.09",
                "end_date": "2019.06",
                "courses": ["数据结构", "操作系统"],
            }
        ],
        "work_experiences": [
            {
                "company_name": "某科技有限公司",
                "position_title": "高级后端开发工程师",
                "start_date": "2021.07",
                "end_date": "至今",
                "is_current": True,
                "responsibilities": ["负责核心交易系统服务治理与性能优化"],
                "achievements": ["接口平均延迟下降 35%"],
                "technologies": ["Python", "FastAPI"],
            }
        ],
        "project_experiences": [
            {
                "project_name": "实时风控平台重构",
                "role": "核心开发",
                "start_date": "2022-03",
                "end_date": "2023-01",
                "responsibilities": ["负责规则服务抽象设计与核心 API 开发"],
                "achievements": ["规则配置效率提升 60%"],
                "technologies": ["FastAPI", "Kafka", "PostgreSQL"],
            }
        ],
        "skills": [
            {
                "name": "Python",
                "category": "编程语言",
                "proficiency": "熟练",
                "years_of_experience": 5.5,
                "last_used": "2026",
            }
        ],
    }


def test_resume_profile_can_initialize_with_defaults() -> None:
    profile = ResumeProfile()

    assert profile.basic_info is None
    assert profile.career_intent is None
    assert profile.educations == []
    assert profile.work_experiences == []
    assert profile.project_experiences == []
    assert profile.skills == []
    assert profile.certificates == []
    assert profile.languages == []
    assert profile.awards == []
    assert profile.internships == []
    assert profile.publications == []
    assert profile.custom_sections == []


def test_resume_profile_can_round_trip_complete_payload() -> None:
    payload = _build_profile_payload()

    profile = ResumeProfile.model_validate(payload)
    restored = ResumeProfile.model_validate(profile.model_dump())

    assert restored.model_dump() == profile.model_dump()
    assert restored.basic_info is not None
    assert restored.basic_info.full_name == "张三"
    assert restored.work_experiences[0].end_date == "至今"
    assert restored.work_experiences[0].is_current is True
    assert restored.project_experiences[0].start_date == "2022-03"
    assert restored.educations[0].start_date == "2015.09"


def test_resume_profile_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ResumeProfile.model_validate({"unknown_field": "unexpected"})


def test_resume_profile_allows_missing_career_intent() -> None:
    profile = ResumeProfile.model_validate(_build_profile_payload())

    assert profile.career_intent is None
    assert profile.work_experiences


def test_resume_profile_json_schema_contains_examples_and_nested_sections() -> None:
    schema = ResumeProfile.model_json_schema()

    assert schema["examples"]
    assert schema["properties"]["work_experiences"]["description"] == "工作经历列表。"
    assert schema["properties"]["project_experiences"]["items"]["$ref"].endswith("ProjectExperience")
    assert schema["properties"]["educations"]["items"]["$ref"].endswith("EducationExperience")

    work_schema = schema["$defs"]["WorkExperience"]
    project_schema = schema["$defs"]["ProjectExperience"]
    education_schema = schema["$defs"]["EducationExperience"]

    assert "公司名称" in work_schema["properties"]["company_name"]["description"]
    assert work_schema["properties"]["end_date"]["examples"] == ["至今"]
    assert project_schema["properties"]["start_date"]["examples"] == ["2022-03"]
    assert education_schema["properties"]["start_date"]["examples"] == ["2015.09"]
