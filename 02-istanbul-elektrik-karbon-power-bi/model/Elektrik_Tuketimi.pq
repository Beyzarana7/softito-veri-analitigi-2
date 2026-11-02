let
  Kaynak = Csv.Document(File.Contents("\\tsclient\pbi\istanbul_aylik_sektorel_elektrik_tuketimi_2020_2026_agustos.csv"),[Delimiter=",", Columns=8, Encoding=65001, QuoteStyle=QuoteStyle.None]),
  #"Yükseltilen üst bilgiler" = Table.PromoteHeaders(Kaynak, [PromoteAllScalars = true]),
  #"Değiştirilen sütun türü" = Table.TransformColumnTypes(#"Yükseltilen üst bilgiler", {{"il", type text}, {"yil", Int64.Type}, {"ay", Int64.Type}, {"tuketici_turu", type text}, {"epdk_orijinal_tur", type text}, {"elektrik_tuketimi_mwh", type number}, {"birim", type text}, {"kaynak", type text}}, "en-US"),
  #"Değer değiştirildi" = Table.ReplaceValue(#"Değiştirilen sütun türü", "Kamu ve Özel Hizmetler Sektörü ile Diğer", "Hizmetler/Ticarethane", Replacer.ReplaceText, {"tuketici_turu"}),
  #"Değer değiştirildi 1" = Table.ReplaceValue(#"Değer değiştirildi", "Tarımsal Faaliyetler", "Tarım", Replacer.ReplaceText, {"tuketici_turu"}),
  #"Özel eklendi" = Table.TransformColumnTypes(Table.AddColumn(#"Değer değiştirildi 1", "Tarih", each #date([yil], [ay], 1)), {{"Tarih", type date}})
in
  #"Özel eklendi"
