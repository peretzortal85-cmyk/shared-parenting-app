import streamlit as st
import json
from pathlib import Path
from collections import defaultdict
from datetime import date

st.set_page_config(page_title="הורות ביחד",page_icon="🏠",layout="wide",initial_sidebar_state="auto")
st.markdown("""
<style>
/* RTL for text, not for Streamlit's structural layout. */
html, body, [data-testid="stAppViewContainer"] {direction:rtl;}
h1,h2,h3,p {text-align:right; overflow-wrap:break-word;}
[data-testid="stMetric"] {background:#f7f8fb;border:1px solid #e5e7eb;padding:12px;border-radius:12px;min-width:0;}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {overflow-wrap:anywhere;}
[data-testid="stSidebar"] {direction:rtl;}
/* Do not override sidebar left/right: Streamlit owns the mobile overlay. */
@media (max-width: 768px) {
  .block-container {padding:1rem .85rem 3rem!important; max-width:100%!important;}
  h1 {font-size:1.45rem!important;line-height:1.35!important;}
  h2,h3 {font-size:1.15rem!important;line-height:1.4!important;}
  [data-testid="stHorizontalBlock"] {flex-wrap:wrap!important;gap:.5rem!important;}
  [data-testid="column"] {min-width:calc(50% - .5rem)!important;flex:1 1 calc(50% - .5rem)!important;}
  [data-testid="stMetricValue"] {font-size:1.35rem!important;}
  [data-testid="stMetricLabel"] {font-size:.8rem!important;}
  [data-testid="stSidebar"] {max-width:min(85vw,320px)!important;}
  [data-testid="stSidebar"] * {overflow-wrap:normal;}
  [data-testid="stDataFrame"] {max-width:100%;overflow-x:auto;}
}
</style>""",unsafe_allow_html=True)

DATA_FILE=Path(__file__).with_name("data.json")
data=json.loads(DATA_FILE.read_text(encoding="utf-8"))
months=sorted(set(r["month"] for r in data))
def money(n): return f"₪{n:,.2f}"
def totals(rows):
    fixed=round(sum(x["charge"] for x in rows if x["type"]=="קבועות"),2)
    shared=round(sum(x["charge"] for x in rows if x["type"]!="קבועות"),2)
    return fixed,shared,round(fixed+shared,2)
by_month={m:[r for r in data if r["month"]==m] for m in months}
pages=["🏠 מבט על","🧾 קבלות","💰 התחשבנות","🔁 חיובים קבועים","📅 חגים והסדרים","📨 בקשות","📊 דוחות","⚙️ הגדרות"]
with st.sidebar:
    st.title("🏠 הורות ביחד")
    st.caption("גרסת הדגמה מקומית · מנהלת")
    page=st.radio("קטגוריות",pages,label_visibility="collapsed")
    st.divider()
    st.caption("נתונים היסטוריים מקובץ האקסל · אין עדיין כניסה מאובטחת")
if page==pages[0]:
    st.title("מבט על · התחשבנות שנתית")
    year=st.selectbox("שנה",sorted({m[:4] for m in months},reverse=True))
    relevant=[m for m in months if m.startswith(year)]
    chosen=st.selectbox("חודש להצגת פירוט",relevant,index=min(len(relevant)-1,max(0,int(date.today().month)-1)) if year==str(date.today().year) else 0,format_func=lambda x:f"{x[5:7]}/{x[:4]}")
    fixed,shared,total=totals(by_month[chosen])
    a,b,c=st.columns(3)
    a.metric("חיובים קבועים · חודש נבחר",money(fixed))
    b.metric("משותפות והתאמות · חודש נבחר",money(shared))
    c.metric("סה״כ חיוב · חודש נבחר",money(total))
    st.subheader(f"סך החיובים לכל חודש בשנת {year}")
    chart=[]
    for m in relevant:
        f,s,t=totals(by_month[m])
        chart.append({"חודש":m[5:7]+"/"+m[:4],"סה״כ":t})
    # Altair lets us display the precise amount above every bar.
    import altair as alt
    import pandas as pd
    df=pd.DataFrame(chart)
    base=alt.Chart(df).encode(x=alt.X("חודש:N",sort=None,title="חודש"),y=alt.Y("סה״כ:Q",title="ש״ח"))
    bars=base.mark_bar()
    labels=base.mark_text(dy=-10).encode(text=alt.Text("סה״כ:Q",format=",.2f"))
    st.altair_chart((bars+labels).properties(height=350),use_container_width=True)
    annual=round(sum(row["סה״כ"] for row in chart),2)
    st.metric(f"סה״כ לשנת {year}",money(annual))
    st.subheader(f"סיכום חודשי לשנת {year}")
    rows=[]
    for m in relevant:
        f,s,t=totals(by_month[m])
        rows.append({"חודש":m[5:7]+"/"+m[:4],"קבועות (₪)":f,"משותפות והתאמות (₪)":s,"סה״כ חיוב (₪)":t})
    st.dataframe(rows,hide_index=True,use_container_width=True)
    st.markdown(f"**סה״כ לשנת {year}: {money(annual)}**")
    st.subheader(f"פירוט חודש {chosen[5:7]}.{chosen[:4]}")
    st.dataframe([{"הוצאה":r["name"],"סוג":r["type"],"סכום מקורי":r["original_amount"],"חלק לתשלום (₪)":r["charge"],"הערות":r["notes"]} for r in by_month[chosen]],hide_index=True,use_container_width=True)
    st.markdown(f"**סה״כ לחודש {chosen[5:7]}.{chosen[:4]}: {money(total)}**")
    st.caption("נתוני היסטוריה מתוך האקסל. חודשים עתידיים עשויים להיות לא סופיים.")
elif page==pages[1]:
    st.title("קבלות")
    st.caption("אפשר להעלות קבלה ולבחור מי נושא בעלות. כרגע זו הדגמה: הקבלה אינה נשמרת ולא נשלחת לאישור.")
    receipt=st.file_uploader("צילום קבלה או PDF",type=["jpg","jpeg","png","pdf"])
    desc=st.text_input("תיאור ההוצאה")
    amount=st.number_input("סכום הקבלה (₪)",min_value=0.0,step=10.0)
    payer=st.radio("מי נושא בהוצאה?",["האב משלם 100%","האם משלמת 100%","חלוקה שווה 50/50"])
    if receipt is not None:
        st.success(f"נבחר קובץ: {receipt.name} (טרם נשמר)")
    if amount>0:
        father,mother=(amount,0) if payer=="האב משלם 100%" else ((0,amount) if payer=="האם משלמת 100%" else (amount/2,amount/2))
        a,b=st.columns(2)
        a.metric("חלק האב",money(father))
        b.metric("חלק האם",money(mother))
    st.info("בשלב הבא נוסיף שמירת קבלות, זיהוי סכומים מתמונה, תיעוד מי שילם בפועל ואישורים.")
elif page==pages[2]:
    st.title("התחשבנות חודשית")
    month=st.selectbox("בחרי חודש",months[::-1])
    f,s,t=totals(by_month[month])
    st.metric("סה״כ חיוב לחודש",money(t))
    st.write(f"חיובים קבועים: {money(f)} | הוצאות משותפות והתאמות: {money(s)}")
    st.dataframe([{"הוצאה":r["name"],"סוג":r["type"],"סכום מקורי":r["original_amount"],"לחיוב האב":r["charge"],"הערות":r["notes"]} for r in by_month[month]],hide_index=True,use_container_width=True)
elif page==pages[3]:
    st.title("חיובים קבועים")
    month=st.selectbox("בחרי חודש",months[::-1])
    st.dataframe([{"חיוב":r["name"],"סכום (₪)":r["charge"]} for r in by_month[month] if r["type"]=="קבועות"],hide_index=True,use_container_width=True)
elif page==pages[6]:
    st.title("דוחות")
    year=st.selectbox("שנה",sorted({m[:4] for m in months},reverse=True))
    rows=[]
    for m in months:
        if m.startswith(year):
            f,s,t=totals(by_month[m])
            rows.append({"חודש":m,"קבועות":f,"משותפות והתאמות":s,"סה״כ":t})
    st.dataframe(rows,hide_index=True,use_container_width=True)
    import csv,io
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=["חודש","קבועות","משותפות והתאמות","סה״כ"])
    writer.writeheader();writer.writerows(rows)
    st.download_button("הורדת סיכום CSV",buf.getvalue().encode("utf-8-sig"),file_name=f"summary_{year}.csv",mime="text/csv")
else:
    st.title(page.split(" ",1)[1])
    st.info("קטגוריה זו תיבנה בשלב הבא.")
