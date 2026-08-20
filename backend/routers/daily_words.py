# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc
from typing import Optional, List
from datetime import date, datetime
from database import get_db
from models import DailyWord, WordCheck, Schedule, Student, Class, Teacher, Settings
from schemas import (
    DailyWordCreate, DailyWordUpdate, DailyWord as DailyWordSchema,
    WordCheckCreate, WordCheckUpdate, WordCheck as WordCheckSchema,
    BatchWordCheckCreate, WordCheckNotificationRequest,
    PaginatedDailyWordResponse, WordItem,
)
from routers.auth import get_current_user, get_current_teaching_assistant_user, User
from routers.schedules import get_students_by_class
from utils.logger import log_operation
from utils.wechat_notifier import wechat_notifier
from utils.email_notifier import email_notifier
import json
import requests as http_requests

router = APIRouter()


# ==================== 单词查询工具 ====================

PART_OF_SPEECH_MAP = {
    "noun": "noun",
    "pronoun": "pronoun",
    "verb": "verb",
    "adjective": "adjective",
    "adverb": "adverb",
    "preposition": "preposition",
    "conjunction": "conjunction",
    "interjection": "interjection",
    "article": "article",
    "determiner": "determiner",
    "numeral": "numeral",
}

def _query_free_dictionary_api(word: str, timeout: int = 10):
    try:
        resp = http_requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        return data
    except Exception:
        return None

def _query_youdao_api(word: str, timeout: int = 10):
    try:
        resp = http_requests.get(
            "https://dict.youdao.com/suggest",
            params={"q": word, "le": "eng", "ver": "2", "doctype": "json"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not isinstance(data, dict):
            return None
        entries = data.get("data", {}).get("entries", [])
        if not entries or not isinstance(entries, list):
            return None
        for entry in entries:
            if entry.get("entry", "").strip().lower() == word.strip().lower():
                return entry
        if entries:
            return entries[0]
        return None
    except Exception:
        return None

def _query_youdao_jsonapi(word: str, timeout: int = 10):
    try:
        resp = http_requests.get(
            "https://dict.youdao.com/jsonapi",
            params={"q": word, "doctype": "json"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None

def _extract_phonetics_from_youdao_jsonapi(data):
    result = {"uk_phonetic": "", "us_phonetic": "", "chinese_meaning": ""}
    if not data:
        return result
    ec = data.get("ec")
    if ec and isinstance(ec, dict):
        word_list = ec.get("word", [])
        if word_list and isinstance(word_list, list):
            word_info = word_list[0]
            uk = word_info.get("ukphone", "")
            us = word_info.get("usphone", "")
            if uk:
                result["uk_phonetic"] = f"/{uk}/"
            if us:
                result["us_phonetic"] = f"/{us}/"
            trs = word_info.get("trs", [])
            if trs and isinstance(trs, list):
                first_tr = trs[0]
                if isinstance(first_tr, dict):
                    tr_list = first_tr.get("tr", [])
                    if tr_list and isinstance(tr_list, list):
                        first_tr_item = tr_list[0]
                        if isinstance(first_tr_item, dict):
                            l_i = first_tr_item.get("l", {})
                            if isinstance(l_i, dict):
                                i_list = l_i.get("i", [])
                                if i_list and isinstance(i_list, list):
                                    result["chinese_meaning"] = str(i_list[0])
    return result

def _normalize_ipa(phonetic: str) -> str:
    if not phonetic:
        return phonetic
    phonetic = phonetic.replace("ɹ", "r")
    return phonetic

def _extract_phonetics_from_dictapi(data):
    result = {"uk_phonetic": "", "us_phonetic": "", "meaning": "", "part_of_speech": [], "chinese_meaning": ""}
    if not data:
        return result

    all_phonetics = []
    for entry in (data if isinstance(data, list) else [data]):
        for p in entry.get("phonetics", []):
            text = p.get("text", "")
            if not text or "/" not in text:
                continue
            audio = p.get("audio", "")
            all_phonetics.append({"text": text, "audio": audio})

    uk_phon = ""
    us_phon = ""
    generic_phon = ""

    for p in all_phonetics:
        text = p["text"]
        audio = p["audio"]
        if audio:
            audio_lower = audio.lower()
            if "-uk_" in audio_lower or "_gb_" in audio_lower or "/uk/" in audio_lower:
                if not uk_phon:
                    uk_phon = text
                continue
            elif "-us_" in audio_lower or "_us_" in audio_lower or "/us/" in audio_lower:
                if not us_phon:
                    us_phon = text
                continue
        if not generic_phon:
            generic_phon = text

    if not uk_phon and not us_phon and generic_phon:
        first_entry = data[0] if isinstance(data, list) else data
        phonetics_list = first_entry.get("phonetics", [])
        uk_count = sum(1 for p in phonetics_list if p.get("audio") and ("-uk_" in p["audio"].lower() or "_gb_" in p["audio"].lower()))
        us_count = sum(1 for p in phonetics_list if p.get("audio") and ("-us_" in p["audio"].lower() or "_us_" in p["audio"].lower()))
        if uk_count > 0 and us_count == 0:
            uk_phon = generic_phon
        elif us_count > 0 and uk_count == 0:
            us_phon = generic_phon
        else:
            uk_phon = generic_phon

    if not uk_phon:
        first_entry = data[0] if isinstance(data, list) else data
        if first_entry.get("phonetic"):
            uk_phon = first_entry["phonetic"]

    uk_phon = _normalize_ipa(uk_phon)
    us_phon = _normalize_ipa(us_phon)

    result["uk_phonetic"] = uk_phon
    result["us_phonetic"] = us_phon

    first_entry = data[0] if isinstance(data, list) else data
    meanings = first_entry.get("meanings", [])
    if meanings:
        pos_list = []
        for meaning_entry in meanings:
            pos = (meaning_entry.get("partOfSpeech") or "").lower()
            if pos in PART_OF_SPEECH_MAP and pos not in pos_list:
                pos_list.append(PART_OF_SPEECH_MAP[pos])
        result["part_of_speech"] = pos_list
        first_meaning = meanings[0]
        definitions = first_meaning.get("definitions", [])
        if definitions:
            result["meaning"] = definitions[0].get("definition", "")

    return result

def _extract_from_youdao_suggest(entry):
    result = {"uk_phonetic": "", "us_phonetic": "", "meaning": "", "part_of_speech": [], "chinese_meaning": ""}
    if not entry:
        return result
    chinese = entry.get("explain", "")
    if chinese:
        result["chinese_meaning"] = chinese
    return result

@router.get("/lookup/{word}")
def lookup_word(
    word: str,
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    word = word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="单词不能为空")

    result = {
        "word": word,
        "uk_phonetic": "",
        "us_phonetic": "",
        "meaning": "",
        "part_of_speech": [],
        "chinese_meaning": "",
    }

    dictapi_data = _query_free_dictionary_api(word, timeout=8)
    if dictapi_data:
        extracted = _extract_phonetics_from_dictapi(dictapi_data)
        result["uk_phonetic"] = extracted["uk_phonetic"]
        result["us_phonetic"] = extracted["us_phonetic"]
        result["meaning"] = extracted["meaning"]
        result["part_of_speech"] = extracted["part_of_speech"]

    youdao_jsonapi_data = _query_youdao_jsonapi(word, timeout=8)
    if youdao_jsonapi_data:
        youdao_phonetics = _extract_phonetics_from_youdao_jsonapi(youdao_jsonapi_data)
        if not result["uk_phonetic"] and youdao_phonetics["uk_phonetic"]:
            result["uk_phonetic"] = youdao_phonetics["uk_phonetic"]
        if not result["us_phonetic"] and youdao_phonetics["us_phonetic"]:
            result["us_phonetic"] = youdao_phonetics["us_phonetic"]
        if youdao_phonetics["chinese_meaning"]:
            result["chinese_meaning"] = youdao_phonetics["chinese_meaning"]

    youdao_entry = _query_youdao_api(word, timeout=8)
    if youdao_entry:
        youdao_result = _extract_from_youdao_suggest(youdao_entry)
        if youdao_result["chinese_meaning"]:
            result["chinese_meaning"] = youdao_result["chinese_meaning"]

    if not result["uk_phonetic"] and not result["chinese_meaning"]:
        raise HTTPException(status_code=404, detail=f"未找到\"{word}\"的相关信息，请手动填写")

    if not result["chinese_meaning"] and result["meaning"]:
        try:
            translate_resp = http_requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": result["meaning"], "langpair": "en|zh-CN"},
                timeout=8,
            )
            if translate_resp.status_code == 200:
                translate_data = translate_resp.json()
                if translate_data.get("responseData", {}).get("translatedText"):
                    result["chinese_meaning"] = translate_data["responseData"]["translatedText"]
        except Exception:
            pass

    return result


PHRASE_TYPE_KEYWORDS = {
    "prepositional_phrase": ["preposition", "prepositional phrase", "pp"],
    "verb_phrase": ["verb phrase", "vp", "phrasal verb"],
    "noun_phrase": ["noun phrase", "np"],
    "adjective_phrase": ["adjective phrase", "adjp", "adjectival phrase"],
    "adverb_phrase": ["adverb phrase", "advp", "adverbial phrase"],
    "infinitive_phrase": ["infinitive", "infinitive phrase", "to-infinitive"],
    "gerund_phrase": ["gerund", "gerund phrase", "-ing form"],
    "participle_phrase": ["participle", "participle phrase", "present participle", "past participle"],
    "conjunction_phrase": ["conjunction", "conjunctive phrase", "correlative conjunction"],
    "clause_phrase": ["clause", "subordinate clause", "relative clause", "that-clause"],
}

SYNTACTIC_ROLE_KEYWORDS = {
    "subject": ["subject", "as subject"],
    "predicate": ["predicate", "as predicate", "predicative"],
    "object": ["object", "as object", "direct object", "indirect object"],
    "predicative": ["predicative", "subject complement", "as predicative"],
    "attributive": ["attributive", "as attributive", "modifier", "as modifier"],
    "adverbial": ["adverbial", "as adverbial", "adverbial modifier"],
    "complement": ["complement", "object complement", "as complement"],
    "appositive": ["appositive", "in apposition", "as appositive"],
    "parenthetical": ["parenthetical", "parenthesis", "as parenthesis"],
}

def _detect_phrase_types(meaning: str, part_of_speech_list: list) -> List[str]:
    detected = []
    meaning_lower = meaning.lower() if meaning else ""
    for ptype, keywords in PHRASE_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in meaning_lower:
                detected.append(ptype)
                break
    for pos in part_of_speech_list:
        pos_lower = pos.lower()
        if pos_lower in ("preposition",):
            if "prepositional_phrase" not in detected:
                detected.append("prepositional_phrase")
        elif pos_lower in ("verb",):
            if "verb_phrase" not in detected:
                detected.append("verb_phrase")
        elif pos_lower in ("noun",):
            if "noun_phrase" not in detected:
                detected.append("noun_phrase")
        elif pos_lower in ("adjective",):
            if "adjective_phrase" not in detected:
                detected.append("adjective_phrase")
        elif pos_lower in ("adverb",):
            if "adverb_phrase" not in detected:
                detected.append("adverb_phrase")
    return detected

def _detect_syntactic_roles(meaning: str) -> List[str]:
    detected = []
    meaning_lower = meaning.lower() if meaning else ""
    for role, keywords in SYNTACTIC_ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in meaning_lower:
                detected.append(role)
                break
    return detected


@router.get("/lookup-phrase/{phrase:path}")
def lookup_phrase(
    phrase: str,
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    phrase = phrase.strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="短语不能为空")

    result = {
        "phrase": phrase,
        "phrase_type": [],
        "syntactic_role": [],
        "meaning": "",
        "chinese_meaning": "",
    }

    youdao_jsonapi_data = _query_youdao_jsonapi(phrase, timeout=8)
    if youdao_jsonapi_data:
        youdao_phonetics = _extract_phonetics_from_youdao_jsonapi(youdao_jsonapi_data)
        if youdao_phonetics["chinese_meaning"]:
            result["chinese_meaning"] = youdao_phonetics["chinese_meaning"]

    youdao_entry = _query_youdao_api(phrase, timeout=8)
    if youdao_entry:
        youdao_result = _extract_from_youdao_suggest(youdao_entry)
        if youdao_result["chinese_meaning"] and not result["chinese_meaning"]:
            result["chinese_meaning"] = youdao_result["chinese_meaning"]

    dictapi_data = _query_free_dictionary_api(phrase, timeout=8)
    if dictapi_data:
        extracted = _extract_phonetics_from_dictapi(dictapi_data)
        if extracted["meaning"]:
            result["meaning"] = extracted["meaning"]

        pos_list = []
        first_entry = dictapi_data[0] if isinstance(dictapi_data, list) else dictapi_data
        for meaning_entry in first_entry.get("meanings", []):
            pos = (meaning_entry.get("partOfSpeech") or "").lower()
            if pos and pos not in pos_list:
                pos_list.append(pos)

        if not result["phrase_type"]:
            detected_types = _detect_phrase_types(result["meaning"], pos_list)
            if detected_types:
                result["phrase_type"] = detected_types

    if not result["phrase_type"]:
        phrase_lower = phrase.lower()
        words = phrase_lower.split()
        if words and words[0] == "to" and len(words) > 1:
            if "infinitive_phrase" not in result["phrase_type"]:
                result["phrase_type"].append("infinitive_phrase")
        prepositions = {"in", "on", "at", "by", "with", "for", "from", "to", "of", "about", "under", "over", "between", "through", "during", "without", "against"}
        if words and words[0] in prepositions:
            if "prepositional_phrase" not in result["phrase_type"]:
                result["phrase_type"].append("prepositional_phrase")

    if not result["syntactic_role"] and result["meaning"]:
        detected_roles = _detect_syntactic_roles(result["meaning"])
        if detected_roles:
            result["syntactic_role"] = detected_roles

    if not result["chinese_meaning"] and result["meaning"]:
        try:
            translate_resp = http_requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": result["meaning"], "langpair": "en|zh-CN"},
                timeout=8,
            )
            if translate_resp.status_code == 200:
                translate_data = translate_resp.json()
                if translate_data.get("responseData", {}).get("translatedText"):
                    result["chinese_meaning"] = translate_data["responseData"]["translatedText"]
        except Exception:
            pass

    if not result["meaning"] and not result["chinese_meaning"]:
        raise HTTPException(status_code=404, detail=f"未找到\"{phrase}\"的相关信息，请手动填写")

    return result


# ==================== 每日单词管理 ====================

@router.get("", response_model=PaginatedDailyWordResponse)
def get_daily_words(
    skip: int = 0,
    limit: int = 100,
    grade: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    query = db.query(DailyWord).options(joinedload(DailyWord.creator))
    if grade:
        query = query.filter(DailyWord.grade == grade)
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(DailyWord.date >= date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(DailyWord.date <= date_to_obj)
        except ValueError:
            pass

    total = query.count()
    daily_words = query.order_by(desc(DailyWord.date), asc(DailyWord.grade)).offset(skip).limit(limit).all()

    result = []
    for dw in daily_words:
        result.append(DailyWordSchema(
            id=dw.id,
            grade=dw.grade,
            date=dw.date,
            words=dw.words if dw.words else [],
            created_by=dw.created_by,
            creator_name=dw.creator.name if dw.creator else None,
            created_at=dw.created_at,
            updated_at=dw.updated_at,
        ))
    return {"items": result, "total": total}


@router.get("/grades")
def get_grades_with_words(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    grades = db.query(DailyWord.grade).distinct().all()
    return [g[0] for g in grades]


@router.get("/{daily_word_id}", response_model=DailyWordSchema)
def get_daily_word(
    daily_word_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    dw = db.query(DailyWord).options(joinedload(DailyWord.creator)).filter(DailyWord.id == daily_word_id).first()
    if not dw:
        raise HTTPException(status_code=404, detail="每日单词不存在")
    return DailyWordSchema(
        id=dw.id,
        grade=dw.grade,
        date=dw.date,
        words=dw.words if dw.words else [],
        created_by=dw.created_by,
        creator_name=dw.creator.name if dw.creator else None,
        created_at=dw.created_at,
        updated_at=dw.updated_at,
    )


@router.post("", response_model=DailyWordSchema)
def create_daily_word(
    data: DailyWordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    existing = db.query(DailyWord).filter(DailyWord.grade == data.grade, DailyWord.date == data.date).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"年级 {data.grade} 在 {data.date} 已有每日单词记录，请编辑已有记录")

    words_data = [w.dict() for w in data.words]
    dw = DailyWord(
        grade=data.grade,
        date=data.date,
        words=words_data,
        created_by=data.created_by or (current_user.teacher_id if current_user.teacher_id else None),
    )
    db.add(dw)
    db.commit()
    db.refresh(dw)
    log_operation(db, "每日单词", "新增", f"年级: {dw.grade}, 日期: {dw.date}, 单词数: {len(words_data)}", current_user.username)
    creator_name = None
    if dw.created_by:
        teacher = db.query(Teacher).filter(Teacher.id == dw.created_by).first()
        creator_name = teacher.name if teacher else None
    return DailyWordSchema(
        id=dw.id,
        grade=dw.grade,
        date=dw.date,
        words=dw.words,
        created_by=dw.created_by,
        creator_name=creator_name,
        created_at=dw.created_at,
        updated_at=dw.updated_at,
    )


@router.put("/{daily_word_id}", response_model=DailyWordSchema)
def update_daily_word(
    daily_word_id: int,
    data: DailyWordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    dw = db.query(DailyWord).filter(DailyWord.id == daily_word_id).first()
    if not dw:
        raise HTTPException(status_code=404, detail="每日单词不存在")

    if data.grade is not None:
        dw.grade = data.grade
    if data.date is not None:
        dw.date = data.date
    if data.words is not None:
        dw.words = [w.dict() for w in data.words]

    db.commit()
    db.refresh(dw)
    log_operation(db, "每日单词", "修改", f"ID: {dw.id}, 年级: {dw.grade}, 日期: {dw.date}", current_user.username)
    creator_name = None
    if dw.created_by:
        teacher = db.query(Teacher).filter(Teacher.id == dw.created_by).first()
        creator_name = teacher.name if teacher else None
    return DailyWordSchema(
        id=dw.id,
        grade=dw.grade,
        date=dw.date,
        words=dw.words,
        created_by=dw.created_by,
        creator_name=creator_name,
        created_at=dw.created_at,
        updated_at=dw.updated_at,
    )


@router.delete("/{daily_word_id}")
def delete_daily_word(
    daily_word_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    dw = db.query(DailyWord).filter(DailyWord.id == daily_word_id).first()
    if not dw:
        raise HTTPException(status_code=404, detail="每日单词不存在")
    db.delete(dw)
    db.commit()
    log_operation(db, "每日单词", "删除", f"ID: {daily_word_id}, 年级: {dw.grade}, 日期: {dw.date}", current_user.username)
    return {"message": "删除成功"}


# ==================== 单词检查 ====================

@router.get("/checks/schedule/{schedule_id}")
def get_schedule_word_checks(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="课程安排不存在")

    class_students = get_students_by_class(db, schedule.class_id, is_active=True)

    existing_checks = db.query(WordCheck).filter(WordCheck.schedule_id == schedule_id).all()
    check_map = {c.student_id: c for c in existing_checks}

    grade_daily_words = {}
    for student in class_students:
        if student.grade and student.grade not in grade_daily_words:
            daily_word = db.query(DailyWord).filter(
                DailyWord.grade == student.grade,
                DailyWord.date == schedule.start_date
            ).first()
            grade_daily_words[student.grade] = daily_word

    result = []
    for student in class_students:
        check = check_map.get(student.id)
        daily_word = grade_daily_words.get(student.grade)
        result.append({
            "student_id": student.id,
            "student_name": student.name,
            "student_grade": student.grade,
            "daily_word_id": check.daily_word_id if check else (daily_word.id if daily_word else None),
            "check_id": check.id if check else None,
            "completion_status": check.completion_status if check else "incomplete",
            "attention_words": check.attention_words if check and check.attention_words else [],
            "notes": check.notes if check else "",
            "checked_by": check.checked_by if check else None,
            "checker_name": None,
            "words": daily_word.words if daily_word else [],
            "phrases": daily_word.phrases if daily_word else [],
        })
        if check and check.checked_by:
            teacher = db.query(Teacher).filter(Teacher.id == check.checked_by).first()
            if teacher:
                result[-1]["checker_name"] = teacher.name

    return {
        "schedule_id": schedule_id,
        "class_id": schedule.class_id,
        "course_name": schedule.course.name if schedule.course else "",
        "class_name": schedule.class_.name if schedule.class_ else "",
        "start_date": str(schedule.start_date),
        "start_time": schedule.start_time,
        "end_time": schedule.end_time,
        "checks": result,
    }


@router.post("/checks/batch")
def batch_save_word_checks(
    data: BatchWordCheckCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == data.schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="课程安排不存在")

    saved_checks = []
    for check_data in data.checks:
        existing = db.query(WordCheck).filter(
            WordCheck.schedule_id == data.schedule_id,
            WordCheck.student_id == check_data.student_id
        ).first()

        if existing:
            if check_data.completion_status is not None:
                existing.completion_status = check_data.completion_status
            if check_data.attention_words is not None:
                existing.attention_words = check_data.attention_words
            if check_data.notes is not None:
                existing.notes = check_data.notes
            if check_data.daily_word_id is not None:
                existing.daily_word_id = check_data.daily_word_id
            existing.checked_by = check_data.checked_by or (current_user.teacher_id if current_user.teacher_id else None)
            saved_checks.append(existing)
        else:
            new_check = WordCheck(
                schedule_id=data.schedule_id,
                student_id=check_data.student_id,
                daily_word_id=check_data.daily_word_id,
                completion_status=check_data.completion_status,
                attention_words=check_data.attention_words,
                notes=check_data.notes,
                checked_by=check_data.checked_by or (current_user.teacher_id if current_user.teacher_id else None),
            )
            db.add(new_check)
            saved_checks.append(new_check)

    db.commit()
    log_operation(db, "单词检查", "批量保存", f"课程安排ID: {data.schedule_id}, 检查数: {len(saved_checks)}", current_user.username)
    return {"message": f"保存成功，共 {len(saved_checks)} 条记录", "count": len(saved_checks)}


@router.post("/checks/notify")
def send_word_check_notification(
    data: WordCheckNotificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teaching_assistant_user),
):
    schedule = db.query(Schedule).filter(Schedule.id == data.schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="课程安排不存在")

    checks = db.query(WordCheck).filter(WordCheck.schedule_id == data.schedule_id).all()
    if not checks:
        raise HTTPException(status_code=400, detail="暂无单词检查记录，请先保存检查结果")

    class_info = schedule.class_
    course_info = schedule.course

    grade_words_map = {}
    for check in checks:
        student = check.student
        if student and student.grade and student.grade not in grade_words_map:
            daily_word = db.query(DailyWord).filter(
                DailyWord.grade == student.grade,
                DailyWord.date == schedule.start_date
            ).first()
            if daily_word:
                grade_words_map[student.grade] = daily_word

    status_map = {"completed": "已完成", "partial": "部分完成", "incomplete": "未完成"}
    check_lines = []
    for check in checks:
        student = check.student
        if not student:
            continue
        status_text = status_map.get(check.completion_status, check.completion_status)
        line = f"- {student.name}（{student.grade or '未知年级'}）：{status_text}"
        if check.attention_words and len(check.attention_words) > 0:
            line += f"，须注意：{', '.join(check.attention_words)}"
        if check.notes:
            line += f"，备注：{check.notes}"
        check_lines.append(line)

    word_list_lines = []
    for grade, dw in grade_words_map.items():
        word_list_lines.append(f"\n【{grade} 单词列表】")
        if dw.words:
            for w in dw.words:
                if isinstance(w, dict):
                    word_text = w.get('word', '')
                    meaning = w.get('meaning', '')
                    phonetic = w.get('phonetic', '')
                    parts = [word_text]
                    if phonetic:
                        parts.append(phonetic)
                    if meaning:
                        parts.append(meaning)
                    word_list_lines.append(f"  {' '.join(parts)}")
                else:
                    word_list_lines.append(f"  {w}")

    message = f"【单词检查通知】\n\n"
    message += f"科目：{course_info.name if course_info else ''}\n"
    message += f"班级：{class_info.name if class_info else ''}\n"
    message += f"日期：{schedule.start_date} {schedule.start_time}-{schedule.end_time}\n\n"
    message += f"单词完成情况：\n"
    message += "\n".join(check_lines)
    message += "\n"
    message += "\n".join(word_list_lines)
    message += "\n\n请同学们注意复习须关注的单词。@所有人"

    results = {"wechat": None, "email": None}

    if data.send_wechat and class_info and class_info.wechat_webhook:
        try:
            settings = db.query(Settings).first()
            enabled_classes = []
            if settings and settings.notification_settings:
                try:
                    notif_config = json.loads(settings.notification_settings)
                    enabled_classes = notif_config.get('enabled_classes', [])
                except Exception:
                    pass

            wechat_notifier.load_config(settings.wechat_webhook_config or "{}" if settings else "{}")
            if settings:
                wechat_notifier.load_promotion_info(
                    website=settings.organization_website or "",
                    wechat_qr=settings.wechat_qrcode or "",
                    work_wechat_qr=settings.work_wechat_qrcode or ""
                )

            result = wechat_notifier.send_message_by_type(
                msg_type="schedule_arrange",
                content=message,
                class_id=class_info.id,
                class_webhook=class_info.wechat_webhook,
                is_markdown=True,
                enabled_classes=enabled_classes,
            )
            results["wechat"] = result
            log_operation(db, "单词检查", "发送微信通知", f"结果: {result}", current_user.username)
        except Exception as e:
            results["wechat"] = {"success": False, "message": str(e)}
            log_operation(db, "单词检查", "发送微信通知失败", str(e), current_user.username, "ERROR")

    if data.send_email:
        try:
            settings = db.query(Settings).first()
            if settings and settings.email_config:
                email_config = json.loads(settings.email_config)
                students = get_students_by_class(db, class_info.id, is_active=True)
                students_with_email = [s for s in students if s.email]

                if students_with_email and email_config.get('smtp_host'):
                    from email.mime.text import MIMEText
                    from email.mime.multipart import MIMEMultipart
                    from email.utils import formataddr
                    import smtplib

                    html_body = f"""
                    <html><body>
                    <div style="max-width:600px;margin:0 auto;padding:20px;">
                        <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;text-align:center;border-radius:10px 10px 0 0;">
                            <h2>📝 单词检查通知</h2>
                        </div>
                        <div style="background:#f9f9f9;padding:20px;border-radius:0 0 10px 10px;">
                            <p><strong>科目：</strong>{course_info.name if course_info else ''}</p>
                            <p><strong>班级：</strong>{class_info.name if class_info else ''}</p>
                            <p><strong>日期：</strong>{schedule.start_date} {schedule.start_time}-{schedule.end_time}</p>
                            <h3>单词完成情况</h3>
                            <table style="width:100%;border-collapse:collapse;">
                                <tr style="background:#409eff;color:white;"><th style="padding:8px;border:1px solid #ddd;">学生</th><th style="padding:8px;border:1px solid #ddd;">年级</th><th style="padding:8px;border:1px solid #ddd;">状态</th><th style="padding:8px;border:1px solid #ddd;">须注意</th><th style="padding:8px;border:1px solid #ddd;">备注</th></tr>
                    """
                    for check in checks:
                        student = check.student
                        if not student:
                            continue
                        status_text = status_map.get(check.completion_status, check.completion_status)
                        attention = ", ".join(check.attention_words) if check.attention_words else "-"
                        html_body += f"""
                            <tr><td style="padding:8px;border:1px solid #ddd;">{student.name}</td>
                            <td style="padding:8px;border:1px solid #ddd;">{student.grade or '-'}</td>
                            <td style="padding:8px;border:1px solid #ddd;">{status_text}</td>
                            <td style="padding:8px;border:1px solid #ddd;">{attention}</td>
                            <td style="padding:8px;border:1px solid #ddd;">{check.notes or '-'}</td></tr>
                        """

                    html_body += "</table>"

                    if grade_words_map:
                        html_body += "<h3>单词列表</h3>"
                        for grade, dw in grade_words_map.items():
                            html_body += f"<h4>{grade}</h4><table style='width:100%;border-collapse:collapse;'><tr style='background:#67c23a;color:white;'><th style='padding:8px;border:1px solid #ddd;'>单词</th><th style='padding:8px;border:1px solid #ddd;'>音标</th><th style='padding:8px;border:1px solid #ddd;'>释义</th></tr>"
                            if dw.words:
                                for w in dw.words:
                                    if isinstance(w, dict):
                                        html_body += f"<tr><td style='padding:8px;border:1px solid #ddd;'>{w.get('word','')}</td><td style='padding:8px;border:1px solid #ddd;'>{w.get('phonetic','')}</td><td style='padding:8px;border:1px solid #ddd;'>{w.get('meaning','')}</td></tr>"
                            html_body += "</table>"

                    html_body += """
                            <p style="margin-top:20px;color:#909399;">请同学们注意复习须关注的单词。</p>
                        </div>
                    </div></body></html>
                    """

                    msg = MIMEMultipart()
                    msg['From'] = formataddr((email_config.get('smtp_from_name', settings.site_name), email_config.get('smtp_user', '')))
                    msg['Subject'] = f"【{settings.site_name}】单词检查通知 - {course_info.name if course_info else ''}"
                    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

                    success_count = 0
                    for student in students_with_email:
                        try:
                            msg['To'] = student.email
                            if email_config.get('smtp_ssl', True):
                                smtp = smtplib.SMTP_SSL(email_config.get('smtp_host', ''), email_config.get('smtp_port', 465))
                            else:
                                smtp = smtplib.SMTP(email_config.get('smtp_host', ''), email_config.get('smtp_port', 465))
                            smtp.login(email_config.get('smtp_user', ''), email_config.get('smtp_password', ''))
                            smtp.send_message(msg)
                            smtp.quit()
                            success_count += 1
                        except Exception as e:
                            log_operation(db, "单词检查", "发送邮件失败", f"学生: {student.email}, 错误: {str(e)}", current_user.username, "ERROR")

                    results["email"] = {"success": True, "message": f"邮件发送成功 {success_count}/{len(students_with_email)}"}
                    log_operation(db, "单词检查", "发送邮件通知", f"成功 {success_count}/{len(students_with_email)}", current_user.username)
        except Exception as e:
            results["email"] = {"success": False, "message": str(e)}
            log_operation(db, "单词检查", "发送邮件通知失败", str(e), current_user.username, "ERROR")

    return {"message": "通知发送完成", "results": results}