import streamlit as st
import json
import io
import csv
import uuid
import re
from datetime import datetime
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import fitz
from pathlib import Path
from datetime import date
import pandas as pd
import altair as alt

st.set_page_config(page_title='הורות ביחד', page_icon='🏠', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
html,body,[data-testid="stAppViewContainer"]{direction:rtl}
h1,h2,h3,p{text-align:right;overflow-wrap:break-word}
[data-testid="stMetric"]{background:#f7f8fb;border:1px solid #e5e7eb;padding:12px;border-radius:12px;min-width:0}
[data-testid="stMetricLabel"],[data-testid="stMetricValue"]{overflow-wrap:anywhere}
@media(max-width:768px){.block-container{padding:1rem .8rem 3rem!important;max-width:100%!important}h1{font-size:1.5rem!important}h2,h3{font-size:1.12rem!important}[data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.5rem!important}[data-testid="column"]{min-width:calc(50% - .5rem)!important;flex:1 1 calc(50% - .5rem)!important}[data-testid="stMetricValue"]{font-size:1.25rem!important}[data-testid="stDataFrame"]{max-width:100%;overflow-x:auto}}
</style>''',unsafe_allow_html=True)

DATA_FILE=Path(__file__).with_name('data.json')
try:
    history=json.loads(DATA_FILE.read_text(encoding='utf-8'))
except (OSError,json.JSONDecodeError) as e:
    st.error('לא ניתן לקרוא את data.json. ודאי שהקובץ נמצא לצד app.py ושיש בו JSON תקין.')
    st.stop()

if 'trial_receipts' not in st.session_state:
    st.session_state.trial_receipts=[]
if 'confirm_delete' not in st.session_state:
    st.session_state.confirm_delete=None

def receipt_text(upload):
    """Extract text from JPG/PNG or digital/scanned PDF; never transmit to an external OCR API."""
    content=upload.getvalue()
    if upload.name.lower().endswith('.pdf'):
        document=fitz.open(stream=content,filetype='pdf')
        if len(document)>5:
            raise ValueError('לניסוי ניתן להעלות PDF עד 5 עמודים.')
        parts=[]
        for page in document:
            txt=page.get_text('text')
            if len(txt.strip())>=40:
                parts.append(txt)
            else:
                pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                img=Image.open(io.BytesIO(pix.tobytes('png')))
                parts.append(pytesseract.image_to_string(img,lang='heb+eng',config='--psm 6'))
        return '\n'.join(parts)
    img=Image.open(io.BytesIO(content)).convert('RGB')
    img=ImageOps.exif_transpose(img)
    if max(img.size)>2400:
        img.thumbnail((2400,2400))
    img=ImageEnhance.Contrast(img).enhance(1.5)
    return pytesseract.image_to_string(img,lang='heb+eng',config='--psm 6')

def parse_receipt(text):
    # Prefer dates formatted DD/MM/YYYY or DD.MM.YYYY; require a valid calendar date.
    dates=[]
    for match in re.finditer(r'(?<!\d)([0-3]?\d)[./-]([01]?\d)[./-](20\d{2}|\d{2})(?!\d)',text):
        day,month,year=map(int,match.groups())
        year=year+2000 if year<100 else year
        try: dates.append(date(year,month,day))
        except ValueError: pass
    found_date=dates[0] if dates else None
    # OCR frequently reads 55.00 as 55,00. Prefer amounts near total/payment labels.
    candidates=[]
    for line in text.splitlines():
        normalized=line.replace('₪',' ')
        for match in re.finditer(r'(?<!\d)(\d{1,5}[.,]\d{2})(?!\d)',normalized):
            value=float(match.group(1).replace(',','.'))
            if value<=0: continue
            label=bool(re.search(r'לתשלום|סה.?כ|סכום|שולם|total|amount|55\.00',line,re.I))
            # Exclude likely dates and timestamps.
            if re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}',line):
                continue
            candidates.append((int(label),value))
    amount=sorted(candidates,reverse=True)[0][1] if candidates else None
    return found_date,amount

months=sorted(set(r['month'] for r in history) | {r['month'] for r in st.session_state.trial_receipts})
if not months:
    st.error('לא נמצאו חודשים בקובץ הנתונים.')
    st.stop()

def money(n): return f'₪{n:,.2f}'

def all_rows():
    rows=list(history)
    for r in st.session_state.trial_receipts:
        rows.append({'month':r['month'],'name':r['description']+' (קבלת ניסוי)','type':'משותפות / התאמות','original_amount':r['amount'],'charge':r['father_share'],'notes':r['allocation']+' | קבלת ניסוי','_receipt_id':r['id']})
    return rows

def rows_for_month(month): return [r for r in all_rows() if r['month']==month]

def totals(rows):
    fixed=round(sum(float(r['charge']) for r in rows if r['type']=='קבועות'),2)
    shared=round(sum(float(r['charge']) for r in rows if r['type']!='קבועות'),2)
    return fixed,shared,round(fixed+shared,2)

def expense_table(rows):
    return [{'הוצאה':r['name'],'סוג':r['type'],'סכום מקורי':r.get('original_amount',0),'לחיוב האב':r['charge'],'הערות':r.get('notes','')} for r in rows]

pages=['🏠 מבט על','🧾 קבלות','💰 התחשבנות','🔁 חיובים קבועים','📅 חגים והסדרים','📨 בקשות','📊 דוחות','⚙️ הגדרות']
st.title('🏠 הורות ביחד')
page=st.selectbox('בחרי קטגוריה',pages)
st.caption('גרסת ניסוי — קבלות חדשות נשמרות זמנית בלבד, ללא חשבונות משתמשים')
st.divider()

if page==pages[0]:
    st.header('מבט על · התחשבנות שנתית')
    year=st.selectbox('שנה',sorted({m[:4] for m in months},reverse=True))
    relevant=[m for m in months if m.startswith(year)]
    default_month=f'{date.today().year}-{date.today().month:02d}'
    chosen=st.selectbox('חודש להצגת פירוט',relevant,index=relevant.index(default_month) if default_month in relevant else 0,format_func=lambda m:m[5:7]+'/'+m[:4])
    fixed,shared,total=totals(rows_for_month(chosen))
    a,b,c=st.columns(3)
    a.metric('חיובים קבועים',money(fixed))
    b.metric('משותפות והתאמות',money(shared))
    c.metric('סה״כ החודש',money(total))
    st.subheader(f'סך החיובים לכל חודש בשנת {year}')
    chart=[{'חודש':m[5:7]+'/'+m[:4],'סה״כ':totals(rows_for_month(m))[2]} for m in relevant]
    df=pd.DataFrame(chart)
    base=alt.Chart(df).encode(x=alt.X('חודש:N',sort=None,title='חודש'),y=alt.Y('סה״כ:Q',title='ש״ח'))
    bars=base.mark_bar()
    # Mobile screens are too narrow for twelve numeric labels. Tooltips show exact values.
    bars=bars.encode(tooltip=[alt.Tooltip('חודש:N'),alt.Tooltip('סה״כ:Q',format=',.2f')])
    st.altair_chart(bars.properties(height=300),use_container_width=True)
    st.caption('לחצי על עמודה בגרף כדי לראות את הסכום המדויק. הסכומים מפורטים גם בטבלה.')
    annual=round(sum(r['סה״כ'] for r in chart),2)
    st.metric(f'סה״כ לשנת {year}',money(annual))
    st.subheader(f'סיכום חודשי לשנת {year}')
    summary=[]
    for m in relevant:
        f,s,t=totals(rows_for_month(m))
        summary.append({'חודש':m[5:7]+'/'+m[:4],'קבועות (₪)':f,'משותפות והתאמות (₪)':s,'סה״כ חיוב (₪)':t})
    st.dataframe(summary,hide_index=True,use_container_width=True)
    st.markdown(f'**סה״כ לשנת {year}: {money(annual)}**')
    st.subheader(f'פירוט חודש {chosen[5:7]}.{chosen[:4]}')
    st.dataframe(expense_table(rows_for_month(chosen)),hide_index=True,use_container_width=True)
    st.markdown(f'**סה״כ לחודש {chosen[5:7]}.{chosen[:4]}: {money(total)}**')

elif page==pages[1]:
    st.header('🧾 קבלות — זיהוי אוטומטי')
    st.info('גרסת ניסוי: זיהוי תאריך וסכום מתמונות ומ־PDF, אישור ידני, הוספה מיידית להתחשבנות ומחיקה. קבלות הניסוי אינן נשמרות לצמיתות.')
    receipt=st.file_uploader('העלי צילום קבלה או PDF',type=['jpg','jpeg','png','pdf'],key='receipt_upload')
    if receipt is not None:
        fingerprint=(receipt.name,len(receipt.getvalue()),hash(receipt.getvalue()))
        if st.session_state.get('ocr_fingerprint')!=fingerprint:
            with st.spinner('קוראת את הקבלה...'):
                try:
                    recognized=receipt_text(receipt)
                    detected_date,detected_amount=parse_receipt(recognized)
                    st.session_state.ocr_fingerprint=fingerprint
                    st.session_state.ocr_date=detected_date or date.today()
                    st.session_state.ocr_amount=float(detected_amount or 0)
                    st.session_state.ocr_text=recognized
                    st.session_state.ocr_success=True
                except Exception as exc:
                    st.session_state.ocr_fingerprint=fingerprint
                    st.session_state.ocr_date=date.today()
                    st.session_state.ocr_amount=0.0
                    st.session_state.ocr_text=''
                    st.session_state.ocr_success=False
                    st.warning('לא הצלחתי לקרוא את הקבלה אוטומטית. אפשר למלא את הפרטים ידנית.')
        if st.session_state.get('ocr_success'):
            st.success('הקריאה הושלמה. בדקי את הפרטים לפני ההוספה.')
        if st.session_state.get('ocr_text'):
            with st.expander('טקסט שזוהה מהקבלה — לבדיקת דיוק'):
                st.text(st.session_state.ocr_text[:5000])
        with st.form('receipt_form'):
            description=st.text_input('תיאור ההוצאה',placeholder='למשל: ציוד לבית הספר')
            purchased=st.date_input('תאריך הקבלה (ניתן לתקן)',value=st.session_state.get('ocr_date',date.today()),format='DD/MM/YYYY')
            amount=st.number_input('סכום הקבלה (₪) — ניתן לתקן',min_value=0.0,value=float(st.session_state.get('ocr_amount',0.0)),step=1.0,format='%.2f')
            allocation=st.radio('מי נושא בתשלום?', ['חלוקה שווה 50/50','האב משלם 100%','האם משלמת 100%'])
            submitted=st.form_submit_button('➕ הוספת קבלה להתחשבנות',type='primary',use_container_width=True)
        if submitted:
            if not description.strip():
                st.error('יש להזין תיאור הוצאה.')
            elif amount<=0:
                st.error('יש לוודא שסכום הקבלה גדול מאפס.')
            else:
                month=purchased.strftime('%Y-%m')
                father=round(amount/2,2) if allocation=='חלוקה שווה 50/50' else (round(amount,2) if allocation=='האב משלם 100%' else 0.0)
                st.session_state.trial_receipts.append({'id':str(uuid.uuid4()),'month':month,'description':description.strip(),'amount':round(amount,2),'allocation':allocation,'father_share':father,'filename':receipt.name,'date':purchased.isoformat()})
                st.success(f'הקבלה נוספה לחודש {month[5:7]}/{month[:4]}! חלק האב: {money(father)}. ניתן לראות אותה מיד בהתחשבנות.')
                st.session_state['nav_page']=pages[1]
    st.subheader('קבלות שהוספת בניסוי')
    if not st.session_state.trial_receipts:
        st.caption('אין עדיין קבלות ניסוי.')
    for r in reversed(st.session_state.trial_receipts):
        with st.container(border=True):
            st.write(f"**{r['description']}** — {r['month'][5:7]}/{r['month'][:4]}")
            st.write(f"קובץ: {r['filename']} | סכום: {money(r['amount'])}")
            st.write(f"{r['allocation']} | חלק האב בהתחשבנות: {money(r['father_share'])}")
            if st.session_state.confirm_delete==r['id']:
                st.warning('למחוק את קבלת הניסוי ולהסיר את הסכום מההתחשבנות?')
                yes,no=st.columns(2)
                if yes.button('כן, למחוק',key='yes_'+r['id'],type='primary'):
                    st.session_state.trial_receipts=[x for x in st.session_state.trial_receipts if x['id']!=r['id']]
                    st.session_state.confirm_delete=None
                    st.rerun()
                if no.button('ביטול',key='no_'+r['id']):
                    st.session_state.confirm_delete=None
                    st.rerun()
            else:
                if st.button('🗑️ מחיקת קבלה',key='delete_'+r['id']):
                    st.session_state.confirm_delete=r['id']
                    st.rerun()
    st.caption('אין עדיין מערכת התחברות: כל מי שניגש לגרסת הניסוי יכול למחוק קבלות בניסוי שלו. אין להעלות קבלות רגישות.')

elif page==pages[2]:
    st.header('התחשבנות חודשית')
    month=st.selectbox('בחרי חודש',months[::-1])
    f,s,t=totals(rows_for_month(month))
    st.metric('סה״כ חיוב לחודש',money(t))
    st.write(f'חיובים קבועים: {money(f)} | הוצאות משותפות והתאמות: {money(s)}')
    st.dataframe(expense_table(rows_for_month(month)),hide_index=True,use_container_width=True)
    st.markdown(f'**סה״כ לחודש: {money(t)}**')

elif page==pages[3]:
    st.header('חיובים קבועים')
    month=st.selectbox('בחרי חודש',months[::-1])
    st.dataframe([{'חיוב':r['name'],'סכום (₪)':r['charge']} for r in rows_for_month(month) if r['type']=='קבועות'],hide_index=True,use_container_width=True)

elif page==pages[6]:
    st.header('דוחות')
    year=st.selectbox('שנה',sorted({m[:4] for m in months},reverse=True))
    rows=[]
    for m in months:
        if m.startswith(year):
            f,s,t=totals(rows_for_month(m))
            rows.append({'חודש':m,'קבועות':f,'משותפות והתאמות':s,'סה״כ':t})
    st.dataframe(rows,hide_index=True,use_container_width=True)
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=['חודש','קבועות','משותפות והתאמות','סה״כ'])
    writer.writeheader();writer.writerows(rows)
    st.download_button('הורדת סיכום CSV',buf.getvalue().encode('utf-8-sig'),file_name=f'summary_{year}.csv',mime='text/csv')
else:
    st.header(page.split(' ',1)[1])
    st.info('קטגוריה זו תיבנה בשלב הבא.')
