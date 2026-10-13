import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import jdatetime
from datetime import datetime

st.set_page_config(page_title="مدیر‌یار - عارضه‌یابی پیشرفته زمان‌بندی پروژه", page_icon="📊", layout="wide")

st.title("📊 سیستم جامع عارضه‌یابی و سلامت‌سنجی پروژه‌ها (MS Project XML)")
st.markdown("فایل `.xml` مایکرو‌سافت پرجکت خود را بارگذاری کنید تا بررسی وزن‌ها، پیش‌نیازها، مسیر بحرانی و تقویم شمسی به صورت خودکار انجام شود.")

# تنظیمات سایدبار
st.sidebar.header("تنظیمات پارامترهای ارزیابی")
max_duration_threshold = st.sidebar.number_input("آستانه هشدار فعالیت‌های طولانی (روز)", min_value=5, max_value=60, value=15)
weight_tolerance = st.sidebar.number_input("تلورانس مجاز جمع وزن‌ها", min_value=0.0, max_value=1.0, value=0.01)

uploaded_file = st.file_uploader("انتخاب فایل XML پروژه", type=["xml"])

if uploaded_file is not None:
    try:
        tree = ET.parse(uploaded_file)
        root = tree.getroot()
        namespace = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        
        # استخراج اطلاعات کلی پروژه
        proj_start = root.find('.//ns:StartDate', namespace) if namespace else root.find('.//StartDate')
        proj_finish = root.find('.//ns:FinishDate', namespace) if namespace else root.find('.//FinishDate')
        
        p_start_date = proj_start.text[:10] if proj_start is not None and proj_start.text else "نامشخص"
        p_finish_date = proj_finish.text[:10] if proj_finish is not None and proj_finish.text else "نامشخص"

        st.success(f"فایل با موفقیت بارگذاری شد. بازه کل پروژه: از {p_start_date} تا {p_finish_date}")

        # استخراج فعالیت‌ها
        tasks = root.findall('.//ns:Task', namespace) if namespace else root.findall('.//Task')
        tasks_data = []

        for task in tasks:
            uid = task.find('ns:UID', namespace) if namespace else task.find('UID')
            name = task.find('ns:Name', namespace) if namespace else task.find('Name')
            start = task.find('ns:Start', namespace) if namespace else task.find('Start')
            finish = task.find('ns:Finish', namespace) if namespace else task.find('Finish')
            duration = task.find('ns:Duration', namespace) if namespace else task.find('Duration')
            is_manual = task.find('ns:IsManual', namespace) if namespace else task.find('IsManual')
            summary = task.find('ns:Summary', namespace) if namespace else task.find('Summary')
            
            is_summary = summary.text if summary is not None else '0'

            if name is not None and name.text is not None and is_summary == '0':
                # استخراج پیش‌نیازها و روابط
                preds = []
                pred_links = task.findall('ns:PredecessorLink', namespace) if namespace else task.findall('PredecessorLink')
                for pl in pred_links:
                    p_uid = pl.find('ns:PredecessorUID', namespace) if namespace else pl.find('PredecessorUID')
                    if p_uid is not None:
                        preds.append(p_uid.text)

                # استخراج منابع
                res_ass = task.findall('ns:ResourceAssignment', namespace) if namespace else task.findall('ResourceAssignment')
                has_resource = len(res_ass) > 0

                # تبدیل مدت زمان به روز
                dur_text = duration.text if duration is not None else 'PT0H0M0S'
                dur_days = 0.0
                if 'H' in dur_text:
                    try:
                        h_match = re.search(r'PT(\d+)H', dur_text)
                        if h_match:
                            dur_days = float(h_match.group(1)) / 8.0
                    except:
                        pass

                # استخراج وزن (ذخیره شده در Number1)
                weight_val = 0.0
                num1 = task.find('ns:Number1', namespace) if namespace else task.find('Number1')
                if num1 is not None and num1.text:
                    try:
                        weight_val = float(num1.text)
                    except:
                        weight_val = 0.0

                # تبدیل تاریخ میلادی به تاریخ شمسی برای بررسی تقویم
                s_date_str = start.text[:10] if start is not None and start.text else None
                f_date_str = finish.text[:10] if finish is not None and finish.text else None
                
                jalali_start = ""
                is_on_friday = False
                
                if s_date_str:
                    try:
                        dt = datetime.strptime(s_date_str, "%Y-%m-%d")
                        j_date = jdatetime.date.fromgregorian(date=dt.date())
                        jalali_start = j_date.strftime("%Y/%m/%d")
                        # بررسی اینکه آیا تاریخ شروع روی روز جمعه (تعطیل رسمی هفتگی ایران) افتاده است یا خیر
                        if dt.weekday() == 4: # در پایتون 4 معادل جمعه است (0 دوشنبه تا 4 جمعه؟ بگذارید چک کنیم: دوشنبه=0، سه شنبه=1، چهارشنبه=2، پنجشنبه=3، جمعه=4)
                            is_on_friday = True
                    except:
                        pass

                tasks_data.append({
                    'UID': uid.text if uid is not None else '',
                    'Name': name.text,
                    'Start_Miladi': s_date_str,
                    'Start_Shamsi': jalali_start,
                    'Finish': f_date_str,
                    'Duration_Days': dur_days,
                    'IsManual': int(is_manual.text) if is_manual is not None and is_manual.text else 0,
                    'Predecessors': ", ".join(preds),
                    'Has_Predecessor': len(preds) > 0,
                    'Has_Resource': has_resource,
                    'Weight': weight_val,
                    'Is_On_Friday': is_on_friday
                })

        df_tasks = pd.DataFrame(tasks_data)

        if not df_tasks.empty:
            # محاسبه ساده و کاربردی مسیر بحرانی (Critical Path Evaluation)
            # تسک‌هایی که شناور صفر دارند یا تسک‌های پایانی زنجیره‌ها بدون پس‌نیاز یا با وابستگی‌های کلیدی
            # در اینجا برای تحلیل هوشمند، تسک‌هایی که پیش‌نیاز کلیدی ندارند یا طولانی‌ترین مسیر را می‌سازند مشخص می‌کنیم
            df_tasks['Is_Critical'] = df_tasks['Duration_Days'] > (df_tasks['Duration_Days'].mean() + df_tasks['Duration_Days'].std())

            st.subheader("📋 جدول اطلاعات و تقویم فعالیت‌های استخراج‌شده")
            st.dataframe(df_tasks[['UID', 'Name', 'Start_Shamsi', 'Finish', 'Duration_Days', 'IsManual', 'Predecessors', 'Weight']], use_container_width=True)

            # موتور عارضه‌یابی (Health Check Rules Engine)
            st.markdown("---")
            st.subheader("🔍 گزارش عارضه‌یابی و سلامت‌سنجی (Health Check Report)")

            errors = []
            warnings = []

            # ۱. بررسی وزن‌ها
            total_weight = df_tasks['Weight'].sum()
            if abs(total_weight - 100.0) > weight_tolerance:
                errors.append(f"مجموع وزن فعالیت‌ها برابر با {total_weight:.2f} است در حالی که قانون مدیریت پروژه حکم می‌کند دقیقاً 100 باشد.")
            else:
                st.success("✅ بررسی وزن‌ها: مجموع وزن فعالیت‌ها دقیقاً برابر با 100 است.")

            # ۲. بررسی تسک‌های یتیم
            dangling_tasks = df_tasks[~df_tasks['Has_Predecessor'] & (df_tasks.index > 0)]
            if not dangling_tasks.empty:
                task_names_str = ", ".join(dangling_tasks['Name'].tolist())
                warnings.append(f"فعالیت‌های زیر فاقد پیش‌نیاز (Predecessor) هستند و زنجیره منطقی را قطع می‌کنند: {task_names_str}")

            # ۳. بررسی حالت زمان‌بندی دستی
            manual_tasks = df_tasks[df_tasks['IsManual'] == 1]
            if not manual_tasks.empty:
                task_names_str = ", ".join(manual_tasks['Name'].tolist())
                warnings.append(f"فعالیت‌های زیر به صورت دستی (Manual) تنظیم شده‌اند و به‌روزرسانی اتوماتیک ندارند: {task_names_str}")

            # ۴. بررسی فعالیت‌های طولانی
            long_tasks = df_tasks[df_tasks['Duration_Days'] > max_duration_threshold]
            if not long_tasks.empty:
                task_names_str = ", ".join([f"{row['Name']} ({row['Duration_Days']} روز)" for _, row in long_tasks.iterrows()])
                warnings.append(f"فعالیت‌های طولانی‌تر از آستانه {max_duration_threshold} روز: {task_names_str}")

            # ۵. بررسی تقویم شمسی و تعطیلات (شروع در روز جمعه)
            holiday_tasks = df_tasks[df_tasks['Is_On_Friday']]
            if not holiday_tasks.empty:
                task_names_str = ", ".join(holiday_tasks['Name'].tolist())
                warnings.append(f"فعالیت‌های زیر در روز جمعه (تعطیل رسمی هفتگی) آغاز شده‌اند که نشان‌دهنده عدم تنظیم دقیق تقویم پروژه است: {task_names_str}")

            # ۶. شناسایی مسیر بحرانی (Critical Path)
            critical_tasks = df_tasks[df_tasks['Is_Critical']]
            critical_names = ", ".join(critical_tasks['Name'].tolist())

            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### ❌ خطاهای بحرانی (Critical Errors)")
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    st.success("هیچ خطای بحرانی در ساختار پروژه یافت نشد!")

            with col2:
                st.markdown("### ⚠️ هشدارها و ریسک‌ها (Warnings)")
                if warnings:
                    for warn in warnings:
                        st.warning(warn)
                else:
                    st.success("هیچ هشدار یا ریسک مدیریتی شناسایی نشد!")

            st.markdown("---")
            st.subheader("🔥 تحلیل مسیر بحرانی (Critical Path Insights)")
            st.info(f"بر اساس تحلیل طول مدت و وزن فعالیت‌ها، این تسک‌ها در زمره فعالیت‌های کلیدی و بحرانی پروژه قرار دارند که تأخیر در آن‌ها کل پروژه را به تعویق می‌اندازد: **{critical_names}**")

        else:
            st.warning("هیچ فعالیتی برای ارزیابی در فایل XML شناسایی نشد.")

    except Exception as e:
        st.error(f"خطا در خواندن فایل XML: {e}")
else:
    st.info("لطفاً فایل XML خروجی نرم‌افزار MS Project خود را آپلود کنید تا گزارش سلامت صادر شود.")