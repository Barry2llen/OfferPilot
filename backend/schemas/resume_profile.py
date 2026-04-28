from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResumeSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResumeBasicInfo(ResumeSchemaModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "full_name": "张三",
                    "headline": "高级后端开发工程师",
                    "gender": "男",
                    "birth_date": "1996-08",
                    "age": 29,
                    "phone": "13800000000",
                    "email": "zhangsan@example.com",
                    "location": "上海市浦东新区",
                    "current_city": "上海",
                    "hukou_city": "杭州",
                    "github_url": "https://github.com/zhangsan",
                    "linkedin_url": "https://www.linkedin.com/in/zhangsan",
                    "portfolio_url": "https://portfolio.example.com/zhangsan",
                    "personal_website": "https://zhangsan.dev",
                }
            ]
        },
    )

    full_name: str | None = Field(
        default=None,
        description="候选人姓名。",
        examples=["张三"],
    )
    headline: str | None = Field(
        default=None,
        description="简历标题或个人职业标签。",
        examples=["高级后端开发工程师"],
    )
    gender: str | None = Field(
        default=None,
        description="候选人性别，保留原文表达。",
        examples=["男"],
    )
    birth_date: str | None = Field(
        default=None,
        description="出生日期或出生年月，保留原文表达。",
        examples=["1996-08"],
    )
    age: int | None = Field(
        default=None,
        description="年龄。",
        examples=[29],
    )
    phone: str | None = Field(
        default=None,
        description="联系电话，保留原文表达。",
        examples=["13800000000"],
    )
    email: str | None = Field(
        default=None,
        description="电子邮箱地址。",
        examples=["zhangsan@example.com"],
    )
    location: str | None = Field(
        default=None,
        description="当前所在地的完整描述。",
        examples=["上海市浦东新区"],
    )
    current_city: str | None = Field(
        default=None,
        description="当前所在城市。",
        examples=["上海"],
    )
    hukou_city: str | None = Field(
        default=None,
        description="户籍所在城市。",
        examples=["杭州"],
    )
    github_url: str | None = Field(
        default=None,
        description="GitHub 主页链接。",
        examples=["https://github.com/zhangsan"],
    )
    linkedin_url: str | None = Field(
        default=None,
        description="LinkedIn 主页链接。",
        examples=["https://www.linkedin.com/in/zhangsan"],
    )
    portfolio_url: str | None = Field(
        default=None,
        description="作品集链接。",
        examples=["https://portfolio.example.com/zhangsan"],
    )
    personal_website: str | None = Field(
        default=None,
        description="个人网站链接。",
        examples=["https://zhangsan.dev"],
    )


class ResumeCareerIntent(ResumeSchemaModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "target_positions": ["后端开发工程师", "平台架构师"],
                    "target_industries": ["企业服务", "金融科技"],
                    "target_cities": ["上海", "杭州"],
                    "target_job_types": ["全职"],
                    "target_level": "高级",
                    "expected_salary": "35k-45k*15",
                    "availability": "两周内到岗",
                    "work_mode": "混合办公",
                }
            ]
        },
    )

    target_positions: list[str] = Field(
        default_factory=list,
        description="目标岗位列表。",
        examples=[["后端开发工程师", "平台架构师"]],
    )
    target_industries: list[str] = Field(
        default_factory=list,
        description="目标行业列表。",
        examples=[["企业服务", "金融科技"]],
    )
    target_cities: list[str] = Field(
        default_factory=list,
        description="目标城市列表。",
        examples=[["上海", "杭州"]],
    )
    target_job_types: list[str] = Field(
        default_factory=list,
        description="目标工作类型列表，如全职、实习、兼职。",
        examples=[["全职"]],
    )
    target_level: str | None = Field(
        default=None,
        description="目标职级或发展阶段。",
        examples=["高级"],
    )
    expected_salary: str | None = Field(
        default=None,
        description="期望薪资，保留原文表达。",
        examples=["35k-45k*15"],
    )
    availability: str | None = Field(
        default=None,
        description="到岗时间或可入职时间，保留原文表达。",
        examples=["两周内到岗"],
    )
    work_mode: str | None = Field(
        default=None,
        description="期望工作方式，如现场办公、远程或混合办公。",
        examples=["混合办公"],
    )


class EducationExperience(ResumeSchemaModel):
    school_name: str = Field(
        description="学校名称。",
        examples=["浙江大学"],
    )
    college_name: str | None = Field(
        default=None,
        description="学院名称。",
        examples=["计算机科学与技术学院"],
    )
    major: str | None = Field(
        default=None,
        description="专业名称。",
        examples=["软件工程"],
    )
    degree: str | None = Field(
        default=None,
        description="学位名称。",
        examples=["工学学士"],
    )
    education_level: str | None = Field(
        default=None,
        description="学历层级。",
        examples=["本科"],
    )
    start_date: str | None = Field(
        default=None,
        description="入学时间，保留原文表达。",
        examples=["2015.09"],
    )
    end_date: str | None = Field(
        default=None,
        description="毕业时间，保留原文表达。",
        examples=["2019.06"],
    )
    is_current: bool = Field(
        default=False,
        description="是否仍在就读。",
        examples=[False],
    )
    gpa: str | None = Field(
        default=None,
        description="GPA 或成绩表现，保留原文表达。",
        examples=["3.8/4.0"],
    )
    rank: str | None = Field(
        default=None,
        description="排名信息，保留原文表达。",
        examples=["前 10%"],
    )
    courses: list[str] = Field(
        default_factory=list,
        description="核心课程列表。",
        examples=[["数据结构", "操作系统"]],
    )
    honors: list[str] = Field(
        default_factory=list,
        description="教育阶段的荣誉或奖项列表。",
        examples=[["校级优秀毕业生", "国家奖学金"]],
    )
    description: str | None = Field(
        default=None,
        description="其他无法稳定结构化的补充说明。",
        examples=["主修方向为分布式系统与数据库。"],
    )


class WorkExperience(ResumeSchemaModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "company_name": "某科技有限公司",
                    "department": "基础平台部",
                    "position_title": "高级后端开发工程师",
                    "employment_type": "全职",
                    "location": "上海",
                    "start_date": "2021.07",
                    "end_date": "至今",
                    "is_current": True,
                    "responsibilities": [
                        "负责核心交易系统服务治理与性能优化",
                        "主导多个通用中台能力建设",
                    ],
                    "achievements": [
                        "接口平均延迟下降 35%",
                        "支撑日均千万级请求稳定运行",
                    ],
                    "technologies": ["Python", "FastAPI", "PostgreSQL", "Redis"],
                }
            ]
        },
    )

    company_name: str = Field(
        description="公司名称。",
        examples=["某科技有限公司"],
    )
    department: str | None = Field(
        default=None,
        description="所属部门名称。",
        examples=["基础平台部"],
    )
    position_title: str | None = Field(
        default=None,
        description="岗位名称或职位头衔。",
        examples=["高级后端开发工程师"],
    )
    employment_type: str | None = Field(
        default=None,
        description="任职类型，如全职、外包、合同工。",
        examples=["全职"],
    )
    location: str | None = Field(
        default=None,
        description="工作地点。",
        examples=["上海"],
    )
    start_date: str | None = Field(
        default=None,
        description="开始时间，保留原文表达。",
        examples=["2021.07"],
    )
    end_date: str | None = Field(
        default=None,
        description="结束时间，保留原文表达。",
        examples=["至今"],
    )
    is_current: bool = Field(
        default=False,
        description="是否仍在该岗位任职。",
        examples=[True],
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        description="岗位职责列表。",
        examples=[["负责核心交易系统服务治理与性能优化"]],
    )
    achievements: list[str] = Field(
        default_factory=list,
        description="工作成果或量化成绩列表。",
        examples=[["接口平均延迟下降 35%"]],
    )
    technologies: list[str] = Field(
        default_factory=list,
        description="工作中使用的技术、工具或平台列表。",
        examples=[["Python", "FastAPI", "PostgreSQL"]],
    )


class InternshipExperience(WorkExperience):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "company_name": "某互联网公司",
                    "department": "推荐算法部",
                    "position_title": "后端开发实习生",
                    "employment_type": "实习",
                    "location": "北京",
                    "start_date": "2020-07",
                    "end_date": "2020-12",
                    "is_current": False,
                    "responsibilities": ["参与推荐服务接口开发与日志治理"],
                    "achievements": ["独立交付 2 个内部工具接口"],
                    "technologies": ["Python", "Flask", "MySQL"],
                }
            ]
        },
    )


class ProjectExperience(ResumeSchemaModel):
    project_name: str = Field(
        description="项目名称。",
        examples=["实时风控平台重构"],
    )
    role: str | None = Field(
        default=None,
        description="项目角色。",
        examples=["核心开发"],
    )
    organization: str | None = Field(
        default=None,
        description="项目所属组织、团队或公司。",
        examples=["某科技有限公司"],
    )
    start_date: str | None = Field(
        default=None,
        description="项目开始时间，保留原文表达。",
        examples=["2022-03"],
    )
    end_date: str | None = Field(
        default=None,
        description="项目结束时间，保留原文表达。",
        examples=["2023-01"],
    )
    is_current: bool = Field(
        default=False,
        description="项目是否仍在进行中。",
        examples=[False],
    )
    project_description: str | None = Field(
        default=None,
        description="项目背景或整体说明。",
        examples=["面向多业务线统一建设风控规则引擎与决策服务。"],
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        description="项目职责列表。",
        examples=[["负责规则服务抽象设计与核心 API 开发"]],
    )
    achievements: list[str] = Field(
        default_factory=list,
        description="项目成果列表。",
        examples=[["规则配置效率提升 60%"]],
    )
    technologies: list[str] = Field(
        default_factory=list,
        description="项目使用的技术栈列表。",
        examples=[["FastAPI", "Kafka", "PostgreSQL"]],
    )
    project_url: str | None = Field(
        default=None,
        description="项目链接或演示地址。",
        examples=["https://demo.example.com/risk-platform"],
    )


class SkillItem(ResumeSchemaModel):
    name: str = Field(
        description="技能名称。",
        examples=["Python"],
    )
    category: str | None = Field(
        default=None,
        description="技能类别，如编程语言、框架、数据库。",
        examples=["编程语言"],
    )
    proficiency: str | None = Field(
        default=None,
        description="熟练度描述，保留原文表达。",
        examples=["熟练"],
    )
    years_of_experience: float | None = Field(
        default=None,
        description="该技能相关经验年限。",
        examples=[5.5],
    )
    last_used: str | None = Field(
        default=None,
        description="最近使用时间，保留原文表达。",
        examples=["2026"],
    )


class CertificateItem(ResumeSchemaModel):
    name: str = Field(
        description="证书名称。",
        examples=["PMP"],
    )
    issuer: str | None = Field(
        default=None,
        description="发证机构。",
        examples=["PMI"],
    )
    issued_date: str | None = Field(
        default=None,
        description="发证时间，保留原文表达。",
        examples=["2023-06"],
    )
    expiry_date: str | None = Field(
        default=None,
        description="到期时间，保留原文表达。",
        examples=["2026-06"],
    )
    credential_id: str | None = Field(
        default=None,
        description="证书编号或凭证 ID。",
        examples=["PMP-1234567"],
    )


class LanguageItem(ResumeSchemaModel):
    name: str = Field(
        description="语言名称。",
        examples=["英语"],
    )
    proficiency: str | None = Field(
        default=None,
        description="语言熟练度描述。",
        examples=["可作为工作语言"],
    )
    score: str | None = Field(
        default=None,
        description="语言考试成绩，保留原文表达。",
        examples=["IELTS 7.5"],
    )


class AwardItem(ResumeSchemaModel):
    name: str = Field(
        description="奖项名称。",
        examples=["国家奖学金"],
    )
    issuer: str | None = Field(
        default=None,
        description="颁发机构。",
        examples=["教育部"],
    )
    date: str | None = Field(
        default=None,
        description="获奖时间，保留原文表达。",
        examples=["2018-12"],
    )
    description: str | None = Field(
        default=None,
        description="奖项说明或获奖原因。",
        examples=["综合成绩与科研表现位列专业前 1%。"],
    )


class PublicationItem(ResumeSchemaModel):
    title: str = Field(
        description="论文、专利或出版物标题。",
        examples=["面向高并发场景的任务调度系统设计"],
    )
    publisher: str | None = Field(
        default=None,
        description="发表机构、期刊或出版方。",
        examples=["软件学报"],
    )
    published_date: str | None = Field(
        default=None,
        description="发表时间，保留原文表达。",
        examples=["2024-05"],
    )
    url: str | None = Field(
        default=None,
        description="出版物链接。",
        examples=["https://example.com/publications/task-scheduler"],
    )
    description: str | None = Field(
        default=None,
        description="出版物简介。",
        examples=["聚焦任务编排系统在高并发业务中的可用性设计。"],
    )


class CustomSection(ResumeSchemaModel):
    section_name: str = Field(
        description="自定义章节名称。",
        examples=["校园经历"],
    )
    items: list[str] = Field(
        default_factory=list,
        description="章节条目列表，保留原文要点。",
        examples=[["担任学生会技术部部长", "组织校级编程比赛"]],
    )


class ResumeProfile(ResumeSchemaModel):
    """
    简历档案模型，包含候选人的结构化信息字段。设计时兼顾信息完整性与模型解析能力，支持多样化的简历内容表达。
    """
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "basic_info": {
                        "full_name": "张三",
                        "headline": "高级后端开发工程师",
                        "phone": "13800000000",
                        "email": "zhangsan@example.com",
                        "current_city": "上海",
                    },
                    "career_intent": {
                        "target_positions": ["后端开发工程师", "平台架构师"],
                        "target_cities": ["上海", "杭州"],
                        "expected_salary": "35k-45k*15",
                        "availability": "两周内到岗",
                    },
                    "educations": [
                        {
                            "school_name": "浙江大学",
                            "major": "软件工程",
                            "education_level": "本科",
                            "start_date": "2015.09",
                            "end_date": "2019.06",
                        }
                    ],
                    "work_experiences": [
                        {
                            "company_name": "某科技有限公司",
                            "position_title": "高级后端开发工程师",
                            "start_date": "2021.07",
                            "end_date": "至今",
                            "is_current": True,
                            "achievements": ["接口平均延迟下降 35%"],
                        }
                    ],
                    "project_experiences": [
                        {
                            "project_name": "实时风控平台重构",
                            "role": "核心开发",
                            "start_date": "2022-03",
                            "end_date": "2023-01",
                            "technologies": ["FastAPI", "Kafka", "PostgreSQL"],
                        }
                    ],
                    "skills": [
                        {
                            "name": "Python",
                            "category": "编程语言",
                            "proficiency": "熟练",
                            "years_of_experience": 5.5,
                        }
                    ],
                    "certificates": [
                        {
                            "name": "PMP",
                            "issuer": "PMI",
                            "issued_date": "2023-06",
                        }
                    ],
                    "languages": [
                        {
                            "name": "英语",
                            "proficiency": "可作为工作语言",
                            "score": "IELTS 7.5",
                        }
                    ],
                    "awards": [
                        {
                            "name": "国家奖学金",
                            "issuer": "教育部",
                            "date": "2018-12",
                        }
                    ],
                    "internships": [
                        {
                            "company_name": "某互联网公司",
                            "position_title": "后端开发实习生",
                            "employment_type": "实习",
                            "start_date": "2020-07",
                            "end_date": "2020-12",
                        }
                    ],
                    "publications": [
                        {
                            "title": "面向高并发场景的任务调度系统设计",
                            "publisher": "软件学报",
                            "published_date": "2024-05",
                        }
                    ],
                    "custom_sections": [
                        {
                            "section_name": "校园经历",
                            "items": ["担任学生会技术部部长"],
                        }
                    ],
                }
            ]
        },
    )

    basic_info: ResumeBasicInfo | None = Field(
        default=None,
        description="候选人的基础个人信息。",
    )
    career_intent: ResumeCareerIntent | None = Field(
        default=None,
        description="候选人的求职意向信息。",
    )
    educations: list[EducationExperience] = Field(
        default_factory=list,
        description="教育经历列表。",
    )
    work_experiences: list[WorkExperience] = Field(
        default_factory=list,
        description="工作经历列表。",
    )
    project_experiences: list[ProjectExperience] = Field(
        default_factory=list,
        description="项目经历列表。",
    )
    skills: list[SkillItem] = Field(
        default_factory=list,
        description="技能条目列表。",
    )
    certificates: list[CertificateItem] = Field(
        default_factory=list,
        description="证书列表。",
    )
    languages: list[LanguageItem] = Field(
        default_factory=list,
        description="语言能力列表。",
    )
    awards: list[AwardItem] = Field(
        default_factory=list,
        description="奖项列表。",
    )
    internships: list[InternshipExperience] = Field(
        default_factory=list,
        description="实习经历列表。",
    )
    publications: list[PublicationItem] = Field(
        default_factory=list,
        description="论文、专利或出版物列表。",
    )
    custom_sections: list[CustomSection] = Field(
        default_factory=list,
        description="无法归入标准章节的自定义信息列表。",
    )


__all__ = [
    "AwardItem",
    "CertificateItem",
    "CustomSection",
    "EducationExperience",
    "InternshipExperience",
    "LanguageItem",
    "ProjectExperience",
    "PublicationItem",
    "ResumeBasicInfo",
    "ResumeCareerIntent",
    "ResumeProfile",
    "SkillItem",
    "WorkExperience",
]
