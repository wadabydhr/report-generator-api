# ... (all your other code unchanged)

# Add this after LANGUAGE_LEVEL_CHOICES:
LEVEL_VALUE_TO_LABEL = {v: k for k, v in LANGUAGE_LEVEL_CHOICES}

# ... inside run_streamlit():
    st.markdown("#### Idiomas e Nível do Candidato")
    language_skills = {}
    for lang in LANGUAGE_DISPLAY:
        col1, col2 = st.columns([1,2])
        with col1:
            label = lang["label_pt"] if language == "PT" else lang["label_en"]
            st.write(f"{label}:")
        with col2:
            level = st.selectbox(
                "",
                options=[choice[1] for choice in LANGUAGE_LEVEL_CHOICES],  # [0,1,2,3,4,5]
                format_func=lambda x: LEVEL_VALUE_TO_LABEL[x],  # now maps 0->"NO", 1->"Elementar", etc.
                key=f"{lang['key']}_level"
            )
            language_skills[lang["key"]] = level