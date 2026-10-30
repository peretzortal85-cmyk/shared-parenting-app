import streamlit as st
import json
import io
import csv
import uuid
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

months=sorted(set(r['month'] for r in history))
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
    st.header('🧾 קבלות')
    st.info('ניסוי זמני: אפשר להוסיף קבלה להתחשבנות ולמחוק אותה. הנתונים והקובץ אינם נשמרים בשרת.')
    with st.form('receipt_form',clear_on_submit=True):
        receipt=st.file_uploader('צילום קבלה או PDF',type=['jpg','jpeg','png','pdf'])
        description=st.text_input('תיאור ההוצאה',placeholder='למשל: ציוד לבית הספר')
        month=st.selectbox('חודש לחיוב',months[::-1],format_func=lambda m:m[5:7]+'/'+m[:4])
        amount=st.number_input('סכום הקבלה (₪)',min_value=0.0,step=10.0)
        allocation=st.radio('מי נושא בתשלום?', ['חלוקה שווה 50/50','האב משלם 100%','האם משלמת 100%'])
        submitted=st.form_submit_button('➕ הוספת קבלה להתחשבנות',type='primary',use_container_width=True)
    if submitted:
        if receipt is None:
            st.error('יש לבחור צילום קבלה או PDF.')
        elif not description.strip():
            st.error('יש להזין תיאור הוצאה.')
        elif amount<=0:
            st.error('יש להזין סכום גדול מאפס.')
        else:
            father=round(amount/2,2) if allocation=='חלוקה שווה 50/50' else (round(amount,2) if allocation=='האב משלם 100%' else 0.0)
            st.session_state.trial_receipts.append({'id':str(uuid.uuid4()),'month':month,'description':description.strip(),'amount':round(amount,2),'allocation':allocation,'father_share':father,'filename':receipt.name})
            st.success('הקבלה נוספה להתחשבנות הניסוי! עברי למבט על או להתחשבנות כדי לראות את הסכום המעודכן.')
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
    st.caption('מחיקה זמינה כאן רק לצורך הדגמה. אין עדיין זיהוי מנהלת או הרשאות מאובטחות.')

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
