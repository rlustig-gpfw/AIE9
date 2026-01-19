from typing import List
import trafilatura

class WebBlogLoader:
    def __init__(self, urls: List[str]):
        self.urls = urls
        self.documents = []

    def load_documents(self) -> List[str]:
        """Iterates through URLs and populates self.documents with the text content of the URLs"""
        for url in self.urls:
            content = self.scrape_url(url)
            if content:
                self.documents.append(content)
        return self.documents

    def scrape_url(self, url: str) -> str:
        """Scrapes the text content of a URL"""
        try:
            text = trafilatura.fetch_url(url)
            result = trafilatura.extract(text, output_format="txt")
            return result
        except Exception as e:
            print(f"Error scraping URL {url}: {e}")
            return None
