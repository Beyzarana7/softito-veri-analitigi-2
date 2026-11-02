let
  Kaynak = Csv.Document(File.Contents("\\tsclient\pbi\Emisyon_Faktorleri.csv"),[Delimiter=";", Columns=4, Encoding=65001, QuoteStyle=QuoteStyle.None]),
  #"Yükseltilen üst bilgiler" = Table.PromoteHeaders(Kaynak, [PromoteAllScalars = true]),
  #"Değiştirilen sütun türü" = Table.TransformColumnTypes(#"Yükseltilen üst bilgiler", {{"yil", Int64.Type}, {"iletim_faktoru", type number}, {"dagitim_faktoru", type number}, {"hesaplama_turu", type text}}, "tr")
in
  #"Değiştirilen sütun türü"
