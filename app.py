import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import jdatetime
from datetime import datetime

# تنظیمات اولیه صفحه
st.set_page_config(page_title="مدیر‌یار - عارضه‌یابی هوشمند زمان‌بندی", page_icon="📈", layout="wide")

# تزریق CSS سفارشی برای ساخت UI مدرن و داشبوردی
st.markdown("""
    <style>
    /* فونت و جهت متن */
    @import url('https://v1.fontapi.ir/css/Vazir');
    html, body, [class*="css"]  {
        font-family: 'Vazir', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    /* استایل کارت‌های شاخص (KPI Cards) */
    .kpi-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border-right: 5px solid #1E88E5;
        margin-bottom: 10px;
    }
    .kpi-title {
        font-size: 14px;
        color: #666;
        margin-bottom: 5px;
    }
    .kpi-value {
        font-size: 24px;
        font-weight: bold;
        color: #111;
    }
    
    /* استایل کارت‌های خطا و هشدار */
    .report-card-error {
        background-color: #FFF5F5;
        border: 1px solid #FEB2B2;
        border-right: 6px solid #E53E3E;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    }
    .report-card-warning {
        background-color: #FFFAF0;
        border: 1px solid #FBD38D;
        border-right: 6px solid #DD6B20;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    }
    .report-card-success {
        background-color: #F0FFF4;
        border: 1px solid #9AE6B4;
        border-right: 6px solid #38A169;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 12px;
    }
    .card-icon {
        font-size: 20px;
        margin-left: 8px;
        vertical-align: middle;
    }
    
    /* هدرهای بخش‌ها */
    .section-header {
        color: #2D3748;
        font-size: 20px;
        font-weight: bold;
        margin-top: 25px;
        margin-bottom: 15px;
        border-bottom: 2px solid #E2E8F0;
        padding-bottom: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# هدر اصلی برنامه
st.title("📈 سیستم جامع عارضه‌یابی و سلامت‌سنجی زمان‌بندی (MS Project)")
st.caption("ابزار هوشمند ارزیابی ساختار منطقی، وزن‌دهی، تقویم شمسی و مسیر بحرانی پروژه‌ها")

# تنظیمات سایدبار
st.sidebar.image("https://img.icons8.com/fluency/96/project-setup.png", width=80)
st.sidebar.header("⚙️ پارامترهای ارزیابی")
max_duration_threshold = st.sidebar.number_input("آستانه فعالیت‌های طولانی (روز)", min_value=5, max_value=60, value=15)
weight_tolerance = st.sidebar.number_input("تلورانس مجاز جمع وزن‌ها", min_value=0.0, max_value=1.0, value=0.01)

uploaded_file = st.file_uploader("📂 انتخاب فایل XML پروژه", type=["xml"])

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

        # شناسایی فیلدهای مربوط به Weight
        weight_field_ids = set()
        ext_attrs = root.findall('.//ns:ExtendedAttribute', namespace) if namespace else root.findall('.//ExtendedAttribute')
        for ext in ext_attrs:
            field_id = ext.find('ns:FieldID', namespace) if namespace else ext.find('FieldID')
            title = ext.find('ns:Title', namespace) if namespace else ext.find('Title')
            cf_name = ext.find('ns:CFName', namespace) if namespace else ext.find('CFName')
            
            title_text = title.text if title is not None and title.text else (cf_name.text if cf_name is not None and cf_name.text else "")
            if field_id is not None and field_id.text and title_text:
                if 'weight' in title_text.lower() or 'وزن' in title_text:
                    weight_field_ids.add(field_id.text)

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
                # پیش‌نیازها
                preds = []
                pred_links = task.findall('ns:PredecessorLink', namespace) if namespace else task.findall('PredecessorLink')
                for pl in pred_links:
                    p_uid = pl.find('ns:PredecessorUID', namespace) if namespace else pl.find('PredecessorUID')
                    if p_uid is not None:
                        preds.append(p_uid.text)

                # منابع
                res_ass = task.findall('ns:ResourceAssignment', namespace) if namespace else task.findall('ResourceAssignment')
                has_resource = len(res_ass) > 0

                # مدت زمان
                dur_text = duration.text if duration is not None else 'PT0H0M0S'
                dur_days = 0.0
                if 'H' in dur_text:
                    try:
                        h_match = re.search(r'PT(\d+)H', dur_text)
                        if h_match:
                            dur_days = float(h_match.group(1)) / 8.0
                    except:
                        pass

                # استخراج وزن
                weight_val = 0.0
                task_ext_attrs = task.findall('ns:ExtendedAttribute', namespace) if namespace else task.findall('ExtendedAttribute')
                for tea in task_ext_attrs:
                    t_field_id = tea.find('ns:FieldID', namespace) if namespace else tea.find('FieldID')
                    t_val = tea.find('ns:Value', namespace) if namespace else tea.find('Value')
                    if t_field_id is not None and t_field_id.text in weight_field_ids and t_val is not None and t_val.text:
                        try:
                            weight_val = float(t_val.text)
                            break
                        except:
                            pass
                
                if weight_val == 0.0:
                    num1 = task.find('ns:Number1', namespace) if namespace else task.find('Number1')
                    if num1 is not None and num1.text:
                        try:
                            weight_val = float(num1.text)
                        except:
                            weight_val = 0.0

                # شمسی‌سازی تاریخ‌ها
                s_date_str = start.text[:10] if start is not None and start.text else None
                f_date_str = finish.text[:10] if finish is not None and finish.text else None
                
                jalali_start = ""
                jalali_finish = ""
                is_on_friday = False
                
                if s_date_str:
                    try:
                        dt = datetime.strptime(s_date_str, "%Y-%m-%d")
                        j_date = jdatetime.date.fromgregorian(date=dt.date())
                        jalali_start = j_date.strftime("%Y/%m/%d")
                        if dt.weekday() == 4:
                            is_on_friday = True
                    except:
                        pass

                if f_date_str:
                    try:
                        dt_f = datetime.strptime(f_date_str, "%Y-%m-%d")
                        j_date_f = jdatetime.date.fromgregorian(date=dt_f.date())
                        jalali_finish = j_date_f.strftime("%Y/%m/%d")
                    except:
                        pass

                tasks_data.append({
                    'UID': uid.text if uid is not None else '',
                    'Name': name.text,
                    'Start_Miladi': s_date_str,
                    'Start_Shamsi': jalali_start,
                    'Finish_Miladi': f_date_str,
                    'Finish_Shamsi': jalali_finish,
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
            df_tasks['Is_Critical'] = df_tasks['Duration_Days'] > (df_tasks['Duration_Days'].mean() + df_tasks['Duration_Days'].std())
            
            # --- بخش ۱: کارت‌های خلاصه وضعیت (KPI Cards) ---
            st.markdown('<div class="section-header">📌 نگاه کلی به برنامه زمان‌بندی</div>', unsafe_allow_html=True)
            
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            
            total_tasks_cnt = len(df_tasks)
            total_weight_sum = df_tasks['Weight'].sum()
            
            # قوانین ارزیابی برای محاسبه تعداد خطاها و هشدارها
            errors = []
            warnings = []

            if abs(total_weight_sum - 100.0) > weight_tolerance:
                errors.append(f"مجموع وزن فعالیت‌ها <b>{total_weight_sum:.2f}٪</b> است (باید دقیقاً ۱۰۰٪ باشد).")

            dangling_tasks = df_tasks[~df_tasks['Has_Predecessor'] & (df_tasks.index > 0)]
            if not dangling_tasks.empty:
                warnings.append(f"تعداد <b>{len(dangling_tasks)} فعالیت</b> فاقد پیش‌نیاز هستند و زنجیره منطقی را قطع کرده‌اند.")

            manual_tasks = df_tasks[df_tasks['IsManual'] == 1]
            if not manual_tasks.empty:
                warnings.append(f"تعداد <b>{len(manual_tasks)} فعالیت</b> در حالت زمان‌بندی دستی (Manual) قرار دارند.")

            long_tasks = df_tasks[df_tasks['Duration_Days'] > max_duration_threshold]
            if not long_tasks.empty:
                warnings.append(f"تعداد <b>{len(long_tasks)} فعالیت</b> طولانی‌تر از آستانه {max_duration_threshold} روز شناسایی شد.")

            holiday_tasks = df_tasks[df_tasks['Is_On_Friday']]
            if not holiday_tasks.empty:
                warnings.append(f"تعداد <b>{len(holiday_tasks)} فعالیت</b> در روز جمعه (تعطیل رسمی) شروع می‌شوند.")

            no_res_tasks = df_tasks[~df_tasks['Has_Resource']]
            if not no_res_tasks.empty:
                warnings.append(f"تعداد <b>{len(no_res_tasks)} فعالیت</b> فاقد تخصیص منبع هستند.")

            with kpi1:
                st.markdown(f'''
                    <div class="kpi-card" style="border-right-color: #3182CE;">
                        <div class="kpi-title">تعداد کل فعالیت‌ها</div>
                        <div class="kpi-value">{total_tasks_cnt} <span style="font-size:14px; font-weight:normal;">تسک</span></div>
                    </div>
                ''', unsafe_allow_html=True)

            with kpi2:
                weight_color = "#38A169" if abs(total_weight_sum - 100.0) <= weight_tolerance else "#E53E3E"
                st.markdown(f'''
                    <div class="kpi-card" style="border-right-color: {weight_color};">
                        <div class="kpi-title">مجموع وزن پروژه</div>
                        <div class="kpi-value" style="color: {weight_color};">{total_weight_sum:.1f}%</div>
                    </div>
                ''', unsafe_allow_html=True)

            with kpi3:
                st.markdown(f'''
                    <div class="kpi-card" style="border-right-color: #E53E3E;">
                        <div class="kpi-title">خطاهای بحرانی</div>
                        <div class="kpi-value" style="color: #E53E3E;">{len(errors)}</div>
                    </div>
                ''', unsafe_allow_html=True)

            with kpi4:
                st.markdown(f'''
                    <div class="kpi-card" style="border-right-color: #DD6B20;">
                        <div class="kpi-title">هشدارها و ریسک‌ها</div>
                        <div class="kpi-value" style="color: #DD6B20;">{len(warnings)}</div>
                    </div>
                ''', unsafe_allow_html=True)

            # --- بخش ۲: نتایج عارضه‌یابی به صورت کارت‌های اختصاصی ---
            st.markdown('<div class="section-header">🔍 گزارش تفکیکی سلامت زمان‌بندی</div>', unsafe_allow_html=True)
            
            col_err, col_warn = st.columns(2)

            with col_err:
                st.subheader("❌ خطاهای بحرانی (Critical Errors)")
                if errors:
                    for err in errors:
                        st.markdown(f'''
                            <div class="report-card-error">
                                <span class="card-icon">🚨</span> {err}
                            </div>
                        ''', unsafe_allow_html=True)
                else:
                    st.markdown('''
                        <div class="report-card-success">
                            <span class="card-icon">✅</span> هیچ خطای بحرانی در ساختار وزن‌ها و الگوی پروژه یافت نشد.
                        </div>
                    ''', unsafe_allow_html=True)

            with col_warn:
                st.subheader("⚠️ هشدارها و کیفیت ساختار (Warnings)")
                if warnings:
                    for warn in warnings:
                        st.markdown(f'''
                            <div class="report-card-warning">
                                <span class="card-icon">⚠️</span> {warn}
                            </div>
                        ''', unsafe_allow_html=True)
                else:
                    st.markdown('''
                        <div class="report-card-success">
                            <span class="card-icon">✅</span> تمام ضوابط استاندارد زمان‌بندی رعایت شده است.
                        </div>
                    ''', unsafe_allow_html=True)

            # --- بخش ۳: تحلیل مسیر بحرانی ---
            st.markdown('<div class="section-header">🔥 فعالیت‌های کلیدی و مسیر بحرانی</div>', unsafe_allow_html=True)
            critical_tasks = df_tasks[df_tasks['Is_Critical']]
            critical_names = " ، ".join(critical_tasks['Name'].tolist()) if not critical_tasks.empty else "فعالیت بحرانی خاصی یافت نشد"
            
            st.info(f"**تسک‌های با ریسک بالایی که تاخیر در آن‌ها پروژه را متوقف می‌سازد:** {critical_names}")

            # --- بخش ۴: جدول تعاملی اطلاعات فعالیت‌ها ---
            st.markdown('<div class="section-header">📋 جدول مدرن فعالیت‌ها و تقویم شمسی</div>', unsafe_allow_html=True)
            
            # تغییر نام ستون‌ها برای نمایش زیبا در جدول
            display_df = df_tasks[['UID', 'Name', 'Start_Shamsi', 'Finish_Shamsi', 'Duration_Days', 'IsManual', 'Predecessors', 'Weight']].copy()
            display_df.columns = ['شناسه (UID)', 'نام فعالیت', 'شروع (شمسی)', 'پایان (شمسی)', 'مدت (روز)', 'زمان‌بندی دستی', 'پیش‌نیازها', 'وزن (٪)']
            
            st.dataframe(
                display_df, 
                use_container_width=True,
                height=350
            )

        else:
            st.warning("هیچ فعالیتی برای ارزیابی در فایل XML شناسایی نشد.")

    except Exception as e:
        st.error(f"خطا در پردازش فایل XML: {e}")
else:
    # نمایش راهنمای صفحه اول
    st.markdown("""
    <div style="text-align: center; padding: 40px; background-color: #F7FAFC; border-radius: 15px; border: 2px dashed #CBD5E0; margin-top: 20px;">
        <img src="https://img.icons8.com/fluency/96/upload-to-cloud.png" width="80"/>
        <h3 style="color: #4A5568; margin-top: 15px;">برای شروع، فایل XML پروژه را آپلود کنید</h3>
        <p style="color: #718096;">این سیستم به صورت خودکار وزن‌ها، تاریخ‌های شمسی، پیش‌نیازها و کیفیت زمان‌بندی شما را ارزیابی می‌کند.</p>
    </div>
    """, unsafe_allow_html=True)